# 배포(웹) 전용 로그인 — src/auth.py의 "데스크톱 앱" 방식은 내 컴퓨터에서만 되는 방식이라,
# Streamlit Cloud처럼 다른 서버에서 돌아가는 경우엔 안 쓰인다. 여기서는 구글이 실제
# 배포 주소(APP_BASE_URL)로 다시 돌려보내주는 "웹 애플리케이션" 방식을 쓴다.
#
# 로그인 정보(credentials)는 파일이 아니라 st.session_state에만 저장한다 — 여러 사람(또는
# 여러 기기)이 같은 배포 주소에 각자 접속할 수 있어서, 한 파일을 공유하면 서로 로그인이
# 섞여버리기 때문이다. 세션이 끝나면(브라우저 탭을 닫으면) 다시 로그인해야 한다.
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import streamlit as st

from src.config import APP_BASE_URL, GOOGLE_WEB_CLIENT_ID, GOOGLE_WEB_CLIENT_SECRET, YOUTUBE_SCOPES


def _client_config() -> dict:
    return {
        "web": {
            "client_id": GOOGLE_WEB_CLIENT_ID,
            "client_secret": GOOGLE_WEB_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [APP_BASE_URL],
        }
    }


def _build_flow() -> Flow:
    if not GOOGLE_WEB_CLIENT_ID or not GOOGLE_WEB_CLIENT_SECRET:
        raise RuntimeError(
            "웹 배포용 Google OAuth 클라이언트(GOOGLE_WEB_CLIENT_ID/GOOGLE_WEB_CLIENT_SECRET)가 "
            "설정되어 있지 않습니다. Streamlit Cloud의 Secrets 설정을 확인하세요."
        )
    return Flow.from_client_config(_client_config(), scopes=YOUTUBE_SCOPES, redirect_uri=APP_BASE_URL)


def get_login_url() -> str:
    """구글 로그인 화면으로 보낼 링크를 만든다."""
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    st.session_state["oauth_state"] = state
    return auth_url


def try_handle_redirect() -> bool:
    """구글 로그인 후 이 앱 주소로 돌아왔을 때(주소에 ?code=... 붙어서 옴) 로그인을
    마무리한다. 성공적으로 로그인 정보를 저장했으면 True를 반환한다."""
    params = st.query_params
    code = params.get("code")
    if not code:
        return False

    flow = _build_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as e:  # noqa: BLE001
        st.error(f"로그인 처리 중 문제가 발생했습니다: {e}")
        st.query_params.clear()
        return False

    st.session_state["credentials"] = json.loads(flow.credentials.to_json())
    st.query_params.clear()
    return True


def is_logged_in() -> bool:
    return "credentials" in st.session_state


def get_credentials() -> Credentials:
    data = st.session_state["credentials"]
    creds = Credentials.from_authorized_user_info(data, YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        st.session_state["credentials"] = json.loads(creds.to_json())
    return creds


def get_youtube_client():
    return build("youtube", "v3", credentials=get_credentials())


def logout() -> None:
    st.session_state.pop("credentials", None)
    st.session_state.pop("oauth_state", None)
