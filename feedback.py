"""YouTubeコメントから視聴者の傾向を要約し、次の台本へ渡す。"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def load_feedback(root: Path) -> dict:
    path = root / os.getenv("FEEDBACK_FILE", "output/feedback.json")
    if not path.exists():
        return {"seen_comment_ids": [], "insights": [], "next_video_ideas": [], "avoid": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen_comment_ids": [], "insights": [], "next_video_ideas": [], "avoid": []}


def update_feedback(root: Path, comments: list[dict[str, object]]) -> dict:
    feedback = load_feedback(root)
    seen = set(feedback.get("seen_comment_ids", []))
    new_comments = [comment for comment in comments if comment.get("id") not in seen]
    if not new_comments:
        return feedback

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return feedback
    current = json.dumps({key: feedback.get(key, []) for key in ("insights", "next_video_ideas", "avoid")}, ensure_ascii=False)
    comment_text = "\n".join(
        f"- {comment['text']}（いいね数: {comment.get('like_count', 0)}）"
        for comment in new_comments
    )
    prompt = f"""あなたはAI VTuberの視聴者分析担当です。
既存の視聴者傾向を、新しいYouTubeコメントを参考に更新してください。
単なる感想の羅列ではなく、複数の意見から再利用できる傾向を抽出してください。
少数の攻撃的な意見だけでキャラクター設定を変えないでください。
必ずJSONだけを返してください。

既存の傾向:
{current}

新しいコメント:
{comment_text}

形式:
{{"insights":["好評な要素や視聴者の好み"],"next_video_ideas":["コメントから生まれた次回案"],"avoid":["反応が弱そう、または繰り返しを避ける要素"]}}
各配列は最大8件。具体的で短い日本語にしてください。"""
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 700},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        raw = result["candidates"][0]["content"]["parts"][0]["text"]
        summary = json.loads(raw)
        for key in ("insights", "next_video_ideas", "avoid"):
            if not isinstance(summary.get(key), list):
                raise ValueError(key)
            feedback[key] = [str(item) for item in summary[key]][:8]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError):
        return feedback

    feedback["seen_comment_ids"] = list(seen | {str(comment.get("id")) for comment in new_comments})[-1000:]
    path = root / os.getenv("FEEDBACK_FILE", "output/feedback.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(feedback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return feedback


def feedback_prompt(feedback: dict) -> str:
    data = {key: feedback.get(key, []) for key in ("insights", "next_video_ideas", "avoid")}
    if not any(data.values()):
        return ""
    return "\n視聴者の反応から得た参考情報（盲目的に従わず、新鮮な内容に応用すること）:\n" + json.dumps(data, ensure_ascii=False)
