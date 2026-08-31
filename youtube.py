import json
import os
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_video(video_path: Path, script: str) -> str:
    """OAuth認証済みのYouTubeチャンネルへ動画をアップロードする。"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube投稿用ライブラリがありません。requirements.txtをインストールしてください。"
        ) from exc

    client_path = Path(os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json"))
    token_path = Path(os.getenv("YOUTUBE_TOKEN", "youtube_token.json"))
    if not client_path.is_absolute():
        client_path = Path(__file__).resolve().parent / client_path
    if not token_path.is_absolute():
        token_path = Path(__file__).resolve().parent / token_path
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
            # GUI環境によってブラウザが自動起動しないため、URLを表示して手動で開く。
            credentials = flow.run_local_server(port=0, open_browser=False)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

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
