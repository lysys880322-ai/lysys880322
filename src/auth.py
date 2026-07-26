# Google OAuth 2.0 로그인 — 최초 1회만 브라우저 로그인 창이 뜨고, 이후에는 token.json에
# 저장된 refresh token으로 자동 재로그인된다. client_secret.json/token.json 둘 다
# .gitignore에 등록되어 있어 실수로 커밋될 일이 없다.
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import GOOGLE_CLIENT_SECRETS_FILE, TOKEN_FILE, YOUTUBE_SCOPES


def _client_secrets_path() -> Path:
    path = Path(GOOGLE_CLIENT_SECRETS_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), YOUTUBE_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return creds

    secrets_path = _client_secrets_path()
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"OAuth 클라이언트 파일을 찾을 수 없습니다: {secrets_path}\n"
            "Google Cloud Console에서 만든 '데스크톱 앱' OAuth 클라이언트 json 파일을 "
            "이 경로에 두거나 .env의 GOOGLE_CLIENT_SECRETS_FILE 값을 수정하세요."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_youtube_client():
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds)


def is_logged_in() -> bool:
    return TOKEN_FILE.exists()


def logout() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
