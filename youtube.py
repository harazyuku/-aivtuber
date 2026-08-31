import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def authorize():
    """YouTube API用の認証情報を取得する。"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "YouTube連携用ライブラリがありません。requirements.txtをインストールしてください。"
        ) from exc

    root = Path(__file__).resolve().parent
    client_path = Path(os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json"))
    token_path = Path(os.getenv("YOUTUBE_TOKEN", "youtube_token.json"))
    if not client_path.is_absolute():
        client_path = root / client_path
    if not token_path.is_absolute():
        token_path = root / token_path
    if not client_path.exists():
        raise RuntimeError(f"Google OAuthの認証ファイルがありません: {client_path}")

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
            credentials = flow.run_local_server(port=0, open_browser=False)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def upload_video(video_path: Path, script: str) -> str:
    """OAuth認証済みのYouTubeチャンネルへ動画をアップロードする。"""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube投稿用ライブラリがありません。requirements.txtをインストールしてください。"
        ) from exc

    credentials = authorize()

    title_prefix = os.getenv("YOUTUBE_TITLE_PREFIX", "落津キナの記録")
    title = f"{title_prefix} {os.getenv('VIDEO_TITLE_SUFFIX', '')}".strip()
    description = script.strip() + "\n\n#AI #VTuber #落津キナ"
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": os.getenv("YOUTUBE_CATEGORY_ID", "22"),
        },
        "status": {
            "privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    youtube = build("youtube", "v3", credentials=credentials)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtu.be/{response['id']}"


def fetch_recent_comments(
    max_videos: int = 20,
    max_comments: int = 100,
    video_days: int = 15,
) -> list[dict[str, object]]:
    """直近video_days日以内の自分の動画からコメントを取得する。"""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("YouTube投稿用ライブラリがありません") from exc

    youtube = build("youtube", "v3", credentials=authorize())
    channel = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channel.get("items", [])
    if not items:
        return []
    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId=uploads_id, maxResults=min(50, max_videos)
    ).execute().get("items", [])

    comments: list[dict[str, object]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=video_days)
    for video in videos:
        published_at = video.get("snippet", {}).get("publishedAt")
        if not published_at:
            continue
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published < cutoff:
            break
        video_id = video["contentDetails"]["videoId"]
        response = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=min(100, max_comments),
            order="relevance", textFormat="plainText",
        ).execute()
        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            text = snippet.get("textDisplay", "").strip()
            if text:
                comments.append({
                    "id": item["id"],
                    "video_id": video_id,
                    "text": text[:500],
                    "like_count": snippet.get("likeCount", 0),
                })
            if len(comments) >= max_comments:
                return comments
    return comments
