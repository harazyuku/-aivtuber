import json
import os
import subprocess
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


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
    prompt = (
        f"{character}\n\n"
        "今日のYouTube Shorts用の台本を1本作ってください。"
        "30〜45秒、300文字以内、音声で読みやすい日本語にしてください。"
        "見出しや箇条書きは不要で、台本本文だけを返してください。"
    )
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": character}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500},
    }).encode()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60, context=HTTPS_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Gemini APIエラー ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Geminiから台本を取得できません: {exc}") from exc


def synthesize(text: str, output_path: Path) -> None:
    base_url = os.getenv("AIVIS_URL", "http://127.0.0.1:10101").rstrip("/")
    speaker = os.getenv("AIVIS_SPEAKER", "")
    if not speaker:
        with urllib.request.urlopen(f"{base_url}/speakers", timeout=5) as response:
            speakers = json.loads(response.read().decode("utf-8"))
        speaker = next(str(style["id"]) for item in speakers for style in item.get("styles", []) if "id" in style)
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
    with urllib.request.urlopen(request, timeout=60) as response:
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
    try:
        vts.connect()
        vts.load_model(os.getenv("VTS_MODEL", "Mayoi"))
        obs.connect()
        obs.start_recording()
        subprocess.run(["afplay", str(audio_path)], check=True)
        recording_path = obs.stop_recording()
        subprocess.run([
            "ffmpeg", "-y", "-i", str(recording_path), "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-shortest", str(video_path),
        ], check=True)
    finally:
        obs.close()
        vts.close()


def main() -> None:
    load_env()
    OUTPUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    script_path = OUTPUT / f"{stamp}.txt"
    audio_path = OUTPUT / f"{stamp}.wav"
    video_path = OUTPUT / f"{stamp}.mp4"
    print("[1/3] 台本を生成しています...", flush=True)
    script = generate_script()
    script_path.write_text(script + "\n", encoding="utf-8")
    print("[2/3] AI音声を生成しています...", flush=True)
    synthesize(script, audio_path)
    print("[3/3] 動画を作成しています...", flush=True)
    if os.getenv("LIVE2D_RECORD", "false").lower() == "true":
        render_live2d(audio_path, video_path)
    else:
        render(audio_path, video_path)
    print(f"完成: {video_path}", flush=True)


if __name__ == "__main__":
    main()
