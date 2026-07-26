import os
from pathlib import Path
from dotenv import load_dotenv

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default: str = "") -> str:
    """내 PC에서 그냥 실행할 땐 .env를, Streamlit Cloud에 배포됐을 땐 그쪽 Secrets 설정을
    읽는다. 둘 다 없으면 default를 쓴다 — 로컬 실행 방식은 이 함수가 생기기 전과 완전히
    동일하게 동작한다(AUTH_MODE 기본값이 'desktop'이라 기존 사용자는 영향 없음)."""
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.getenv(key, default)


GOOGLE_CLIENT_SECRETS_FILE = _get("GOOGLE_CLIENT_SECRETS_FILE", "client_secret.json")
GEMINI_API_KEY = _get("GEMINI_API_KEY", "")
GEMINI_MODEL = _get("GEMINI_MODEL", "gemini-flash-latest")

# ── 웹 배포(Streamlit Cloud 등) 전용 설정 — 내 PC에서 그냥 실행할 때는 전혀 안 쓰인다. ──
# AUTH_MODE: "desktop"(기본값, 내 PC 전용 로그인) 또는 "web"(배포용 로그인)
AUTH_MODE = _get("AUTH_MODE", "desktop")
GOOGLE_WEB_CLIENT_ID = _get("GOOGLE_WEB_CLIENT_ID", "")
GOOGLE_WEB_CLIENT_SECRET = _get("GOOGLE_WEB_CLIENT_SECRET", "")
APP_BASE_URL = _get("APP_BASE_URL", "http://localhost:8501")
# 비어있으면(로컬 실행 기본값) 비밀번호 화면 자체를 건너뛴다.
ACCESS_PASSWORD = _get("ACCESS_PASSWORD", "")

TOKEN_FILE = BASE_DIR / "token.json"

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube"]

# 체크박스로 고를 수 있는 번역 대상 언어 — (언어 코드, 화면 표시용 한국어 이름, 프롬프트용 영어 이름)
TARGET_LANGUAGES = [
    ("en", "영어", "English"),
    ("ja", "일본어", "Japanese"),
    ("es", "스페인어", "Spanish"),
    ("pt", "포르투갈어", "Portuguese"),
    ("hi", "힌디어", "Hindi"),
    ("id", "인도네시아어", "Indonesian"),
    ("de", "독일어", "German"),
    ("fr", "프랑스어", "French"),
]

LANGUAGE_NAME_BY_CODE = {code: name_ko for code, name_ko, _ in TARGET_LANGUAGES}
LANGUAGE_ENGLISH_BY_CODE = {code: name_en for code, _, name_en in TARGET_LANGUAGES}
