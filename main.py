import json
import os
import random
import re
import subprocess
import ssl
import time
import wave
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from feedback import feedback_prompt, load_feedback, update_feedback


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
HTTPS_CONTEXT = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def generate_script() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEYが設定されていません")
    character = (ROOT / "prompts/character.txt").read_text(encoding="utf-8")
    feedback = load_feedback(ROOT)
    topics = [
        line.strip()
        for line in (ROOT / "prompts/topics.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    topic = random.choice(topics)
    duration = os.getenv("SCRIPT_DURATION", "約1分")
    min_chars = int(os.getenv("SCRIPT_MIN_CHARS", "320"))
    max_chars = int(os.getenv("SCRIPT_MAX_CHARS", "420"))
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    last_script = ""
    for attempt in range(3):
        retry_note = "" if attempt == 0 else "前回の出力が短すぎました。条件を必ず守ってください。"
        prompt = (
            "今日のYouTube動画用の台本を1本作ってください。"
            f"長さは{duration}、文字数は必ず{min_chars}〜{max_chars}文字にしてください。"
            f"今回のテーマは「{topic}」です。"
            "導入、具体的な出来事、少しずれた気づき、静かな締めの順に展開してください。"
            "最初から最後まで、最低でも8文ある完成した台本にしてください。"
            "音声で読みやすい自然な日本語にしてください。"
            "見出し、箇条書き、文字数報告、制作メモなどは不要です。"
            "台本本文だけを出力してください。"
            + feedback_prompt(feedback)
            + retry_note
        )
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": character}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 2000,
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        }).encode()
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60, context=HTTPS_CONTEXT) as response:
                data = json.loads(response.read().decode("utf-8"))
            last_script = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if min_chars <= len(last_script) <= max_chars:
                return last_script
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Gemini APIエラー ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Geminiから台本を取得できません: {exc}") from exc
    raise RuntimeError(f"Geminiが{min_chars}〜{max_chars}文字の台本を生成できませんでした（最終結果: {len(last_script)}文字）")


def synthesize(text: str, output_path: Path) -> None:
    base_url = os.getenv("AIVIS_URL", "http://127.0.0.1:10101").rstrip("/")
    speaker = os.getenv("AIVIS_SPEAKER", "")
    speaker_name = os.getenv("AIVIS_SPEAKER_NAME", "").strip()
    if not speaker:
        with urllib.request.urlopen(f"{base_url}/speakers", timeout=5) as response:
            speakers = json.loads(response.read().decode("utf-8"))
        styles = [
            (item, style)
            for item in speakers
            for style in item.get("styles", [])
            if "id" in style
        ]
        if speaker_name:
            match = next(
                ((item, style) for item, style in styles
                 if item.get("name") == speaker_name or style.get("name") == speaker_name),
                None,
            )
            if match is None:
                raise RuntimeError(f"AivisSpeechに話者が見つかりません: {speaker_name}")
            _, selected_style = match
            speaker = str(selected_style["id"])
        else:
            speaker = str(styles[0][1]["id"])
    query_url = f"{base_url}/audio_query?text={urllib.parse.quote(text)}&speaker={speaker}"
    query_request = urllib.request.Request(query_url, method="POST")
    with urllib.request.urlopen(query_request, timeout=10) as response:
        query = response.read()
    request = urllib.request.Request(
        f"{base_url}/synthesis?speaker={speaker}",
        data=query,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 初回はモデル読み込みに時間がかかるため、十分な待ち時間を確保する。
    with urllib.request.urlopen(request, timeout=180) as response:
        output_path.write_bytes(response.read())


def render(audio_path: Path, video_path: Path) -> None:
    image = Path(os.getenv("AVATAR_IMAGE", "assets/avatar.png"))
    if not image.is_absolute():
        image = ROOT / image
    if not image.exists():
        raise RuntimeError(f"アバター画像がありません: {image}")
    width = os.getenv("VIDEO_WIDTH", "1080")
    height = os.getenv("VIDEO_HEIGHT", "1920")
    fps = os.getenv("VIDEO_FPS", "30")
    command = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio_path),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-r", fps, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(video_path),
    ]
    subprocess.run(command, check=True)


def render_live2d(audio_path: Path, video_path: Path) -> None:
    from obs import OBS
    from vtube import VTubeStudio

    vts = VTubeStudio(
        os.getenv("VTS_URL", "ws://127.0.0.1:8001"),
        ROOT / ".vtube_studio_token",
        os.getenv("VTS_PLUGIN_NAME", "Auto AI VTuber"),
        os.getenv("VTS_PLUGIN_DEVELOPER", "Auto AI VTuber Dev"),
    )
    obs = OBS(os.getenv("OBS_URL", "ws://127.0.0.1:4455"), os.getenv("OBS_PASSWORD", ""))
    recording_path = None
    # OBSの録画開始が音声再生よりわずかに先行するため、完成動画の音声を補正する。
    audio_sync_delay = float(os.getenv("AUDIO_SYNC_DELAY", "0.15"))
    try:
        vts.connect()
        vts.load_model(os.getenv("VTS_MODEL", "Mayoi"))
        # ModelLoadRequestの返答後も描画が完了するまで少し時間がかかる。
        model_ready_delay = float(os.getenv("VTS_MODEL_READY_DELAY", "2.0"))
        time.sleep(model_ready_delay)
        obs.connect()
        obs.start_recording()
        parameter_id = os.getenv("VTS_MOUTH_PARAMETER", "AutoMouth")
        vts.ensure_custom_parameter(parameter_id)
        with wave.open(str(audio_path), "rb") as audio:
            sample_rate = audio.getframerate()
            chunk_frames = max(1, sample_rate // 20)
            player = subprocess.Popen(["afplay", str(audio_path)])
            try:
                while player.poll() is None:
                    frames = audio.readframes(chunk_frames)
                    if not frames:
                        break
                    samples = memoryview(frames).cast("h")
                    rms = (sum(sample * sample for sample in samples) / max(1, len(samples))) ** 0.5 / 32768
                    mouth = max(0.0, min(1.0, (rms - 0.015) * 18))
                    vts.inject_mouth(mouth, parameter_id)
                    time.sleep(0.05)
                player.wait()
            finally:
                if player.poll() is None:
                    player.terminate()
                vts.inject_mouth(0.0, parameter_id)
        recording_path = obs.stop_recording()
        subprocess.run([
            "ffmpeg", "-y", "-i", str(recording_path),
            "-itsoffset", str(audio_sync_delay), "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-shortest", str(video_path),
        ], check=True)
    finally:
        obs.close()
        vts.close()


def add_subtitles(video_path: Path, script: str, audio_path: Path) -> Path:
    """台本を簡易タイミングで字幕化し、動画へ焼き込む。"""
    ffmpeg = os.getenv("FFMPEG_FULL_BIN", "/usr/local/opt/ffmpeg-full/bin/ffmpeg")
    if not Path(ffmpeg).exists():
        ffmpeg = "ffmpeg"
    subtitle_path = video_path.with_suffix(".srt")
    captioned_path = video_path.with_name(f"{video_path.stem}_captioned{video_path.suffix}")
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])\s*", script) if part.strip()]
    if not sentences:
        sentences = [script.strip()]
    with wave.open(str(audio_path), "rb") as audio:
        total_seconds = audio.getnframes() / audio.getframerate()
    total_weight = sum(len(sentence) for sentence in sentences) or 1
    elapsed = 0.0
    srt_lines = []
    for index, sentence in enumerate(sentences, start=1):
        duration = total_seconds * len(sentence) / total_weight
        start = elapsed
        end = total_seconds if index == len(sentences) else elapsed + duration
        wrapped = "\n".join(sentence[i:i + 18] for i in range(0, len(sentence), 18))
        srt_lines.extend([
            str(index),
            f"{format_srt_time(start)} --> {format_srt_time(end)}",
            wrapped,
            "",
        ])
        elapsed = end
    subtitle_path.write_text("\n".join(srt_lines), encoding="utf-8")
    style = (
        "FontName=Hiragino Sans,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,"
        "Alignment=2,MarginV=70"
    ).replace(",", r"\,")
    subtitle_filter = f"subtitles={subtitle_path}:force_style={style}"
    subprocess.run([
        ffmpeg, "-y", "-i", str(video_path), "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy", str(captioned_path),
    ], check=True)
    return captioned_path


def format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def main() -> None:
    load_env()
    OUTPUT.mkdir(exist_ok=True)
    if os.getenv("LEARN_FROM_YOUTUBE", "true").lower() == "true":
        try:
            from youtube import fetch_recent_comments
            comments = fetch_recent_comments(
                int(os.getenv("FEEDBACK_MAX_VIDEOS", "5")),
                int(os.getenv("FEEDBACK_MAX_COMMENTS", "100")),
            )
            update_feedback(ROOT, comments)
            print(f"[FEEDBACK] コメントを確認しました: {len(comments)}件", flush=True)
        except Exception as exc:
            print(f"[FEEDBACK] コメント取得をスキップしました: {exc}", flush=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    script_path = OUTPUT / f"{stamp}.txt"
    audio_path = OUTPUT / f"{stamp}.wav"
    video_path = OUTPUT / f"{stamp}.mp4"
    print("[1/3] 台本を生成しています...", flush=True)
    script = generate_script()
    script_path.write_text(script + "\n", encoding="utf-8")
    if os.getenv("SCRIPT_ONLY", "false").lower() == "true":
        print(f"台本を保存しました: {script_path}", flush=True)
        return
    print("[2/3] AI音声を生成しています...", flush=True)
    synthesize(script, audio_path)
    print("[3/3] 動画を作成しています...", flush=True)
    if os.getenv("LIVE2D_RECORD", "false").lower() == "true":
        render_live2d(audio_path, video_path)
    else:
        render(audio_path, video_path)
    if os.getenv("BURN_SUBTITLES", "true").lower() == "true":
        video_path = add_subtitles(video_path, script, audio_path)
    print(f"完成: {video_path}", flush=True)
    if os.getenv("UPLOAD_TO_YOUTUBE", "false").lower() == "true":
        from youtube import upload_video
        print("[4/4] YouTubeへ投稿しています...", flush=True)
        youtube_url = upload_video(video_path, script)
        print(f"投稿完了: {youtube_url}", flush=True)


if __name__ == "__main__":
    main()
