# 유튜브 다국어 제목·설명 자동 번역 등록 프로그램
# 실행(내 PC): streamlit run app.py
# 배포(Streamlit Cloud) 시에는 Secrets에서 AUTH_MODE=web, ACCESS_PASSWORD,
# GOOGLE_WEB_CLIENT_ID/SECRET, APP_BASE_URL을 설정해야 한다 — 자세한 내용은 README 참고.
import pandas as pd
import streamlit as st

from src import youtube_api
from src.config import TARGET_LANGUAGES, LANGUAGE_NAME_BY_CODE, AUTH_MODE, ACCESS_PASSWORD
from src.translator import translate_title_and_description

# AUTH_MODE에 따라 "내 PC 전용" 로그인 모듈과 "배포용" 로그인 모듈 중 하나를 그대로
# auth라는 이름으로 쓴다 — 둘 다 is_logged_in()/get_youtube_client()/logout() 이름이
# 똑같아서, 아래 코드는 어느 쪽이든 그대로 동작한다.
if AUTH_MODE == "web":
    from src import auth_web as auth
else:
    from src import auth

st.set_page_config(page_title="ys-유튜브다국어 제목 설명 자동 번역 등록기!!", layout="wide", page_icon="🌏")

# ── 세련된 다크 테마 + 포인트 컬러 스타일 ─────────────────────
st.markdown(
    """
    <style>
    :root {
        --accent1: #7C5CFF;
        --accent2: #22D3EE;
    }
    .stApp {
        background:
            radial-gradient(1200px 600px at 8% -10%, rgba(124,92,255,0.16), transparent),
            radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,0.12), transparent),
            #0b0b12;
    }
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, var(--accent2), var(--accent1));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        padding-bottom: 4px;
    }
    h2 {
        font-weight: 700 !important;
        border-left: 5px solid var(--accent1);
        padding: 2px 0 2px 14px !important;
        margin-top: 2.2rem !important;
        color: #f1f1f6 !important;
    }
    div.stButton > button, .stLinkButton a {
        border-radius: 10px !important;
        border: 1px solid rgba(124,92,255,0.45) !important;
        transition: all 0.15s ease;
        font-weight: 600 !important;
    }
    div.stButton > button:hover {
        border-color: var(--accent1) !important;
        color: var(--accent1) !important;
        transform: translateY(-1px);
    }
    div.stButton > button[kind="primary"], .stLinkButton a {
        background: linear-gradient(90deg, var(--accent1), var(--accent2)) !important;
        border: none !important;
        color: white !important;
        box-shadow: 0 4px 16px rgba(124,92,255,0.35);
    }
    div.stButton > button[kind="primary"]:hover, .stLinkButton a:hover {
        filter: brightness(1.12);
        color: white !important;
    }
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
    }
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border-radius: 12px !important;
        overflow: hidden;
        border: 1px solid rgba(124,92,255,0.2) !important;
    }
    hr, [data-testid="stDivider"] {
        border-color: rgba(124,92,255,0.3) !important;
    }
    [data-testid="stCheckbox"] label p {
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 배포용 비밀번호 게이트 — ACCESS_PASSWORD가 설정된 경우(배포 환경)에만 동작한다.
# 내 PC에서 그냥 실행할 땐 이 값이 비어있어서 아래 블록 전체를 건너뛴다.
if ACCESS_PASSWORD and not st.session_state.get("password_ok"):
    st.title("🔒 접속 비밀번호")
    pw = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("확인"):
        if pw == ACCESS_PASSWORD:
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

st.title("🌏 ys-유튜브다국어 제목 설명 자동 번역 등록기!!")

# 웹 모드에서는 구글 로그인 후 이 주소(?code=...)로 돌아오므로, 매번 먼저 확인한다.
if AUTH_MODE == "web":
    auth.try_handle_redirect()

# ── 세션 상태 초기값 ─────────────────────────────────────────
if "youtube" not in st.session_state:
    st.session_state.youtube = None
if "videos" not in st.session_state:
    st.session_state.videos = []
if "translation_rows" not in st.session_state:
    st.session_state.translation_rows = []  # 화면 표에 보여줄 번역 결과(수정 가능)
if "video_details_cache" not in st.session_state:
    st.session_state.video_details_cache = {}  # video_id -> {snippet, localizations}
if "results" not in st.session_state:
    st.session_state.results = []


def get_client():
    if st.session_state.youtube is None:
        st.session_state.youtube = auth.get_youtube_client()
    return st.session_state.youtube


# ── 1단계: 로그인 ───────────────────────────────────────────
st.header("1. Google 계정 로그인")
if auth.is_logged_in():
    st.success("로그인되어 있습니다.")
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("로그아웃"):
            auth.logout()
            st.session_state.youtube = None
            st.rerun()
elif AUTH_MODE == "web":
    st.info("아래 버튼을 누르면 Google 로그인 화면으로 이동합니다. 로그인·권한 허용 후 자동으로 이 화면으로 돌아옵니다.")
    try:
        login_url = auth.get_login_url()
        st.link_button("Google로 로그인", login_url)
    except RuntimeError as e:
        st.error(str(e))
else:
    st.info("아래 버튼을 누르면 브라우저 창이 열리고 Google 로그인 화면이 나타납니다. 최초 1회만 진행하면 됩니다.")
    if st.button("Google로 로그인"):
        try:
            get_client()
            st.rerun()
        except FileNotFoundError as e:
            st.error(str(e))

if not auth.is_logged_in():
    st.stop()

try:
    youtube = get_client()
except Exception as e:  # noqa: BLE001
    st.error(f"로그인 정보가 만료되었거나 문제가 있습니다: {e}")
    st.stop()

# ── 2단계: 내 영상 목록 불러오기 ────────────────────────────
st.header("2. 번역할 영상 선택")
col1, col2 = st.columns([1, 5])
with col1:
    if st.button("영상 목록 불러오기 / 새로고침"):
        with st.spinner("내 채널 영상 목록을 불러오는 중..."):
            st.session_state.videos = youtube_api.list_my_videos(youtube)

if not st.session_state.videos:
    st.info("왼쪽 '영상 목록 불러오기' 버튼을 눌러주세요.")
    st.stop()

video_df = pd.DataFrame(st.session_state.videos)
video_df.insert(0, "선택", False)
edited_video_df = st.data_editor(
    video_df[["선택", "title", "video_id"]],
    column_config={
        "선택": st.column_config.CheckboxColumn("선택"),
        "title": st.column_config.TextColumn("제목", disabled=True),
        "video_id": st.column_config.TextColumn("영상 ID", disabled=True),
    },
    hide_index=True,
    use_container_width=True,
    key="video_picker",
)
selected_videos = edited_video_df[edited_video_df["선택"]]

if selected_videos.empty:
    st.info("번역할 영상을 하나 이상 선택하세요.")
    st.stop()

# ── 3단계: 번역할 언어 선택 ──────────────────────────────────
st.header("3. 번역할 언어 선택")
lang_cols = st.columns(4)
selected_langs = []
for i, (code, name_ko, _) in enumerate(TARGET_LANGUAGES):
    with lang_cols[i % 4]:
        if st.checkbox(f"{name_ko} ({code})", key=f"lang_{code}"):
            selected_langs.append(code)

if not selected_langs:
    st.info("번역할 언어를 하나 이상 선택하세요.")
    st.stop()

# ── 4단계: 번역 실행 ─────────────────────────────────────────
st.header("4. 번역 실행 및 검토")

if st.button("🌐 선택한 영상 번역하기", type="primary"):
    rows = []
    progress = st.progress(0.0, text="번역 준비 중...")
    selected_ids = selected_videos["video_id"].tolist()

    for idx, video_id in enumerate(selected_ids):
        video_title = selected_videos[selected_videos["video_id"] == video_id]["title"].iloc[0]
        progress.progress((idx) / len(selected_ids), text=f"'{video_title}' 정보 확인 중...")

        details = youtube_api.get_video_full_details(youtube, video_id)
        st.session_state.video_details_cache[video_id] = details
        existing_localizations = details["localizations"]
        snippet = details["snippet"]

        progress.progress((idx + 0.3) / len(selected_ids), text=f"'{video_title}' 번역 중...")
        try:
            translated = translate_title_and_description(
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                target_lang_codes=selected_langs,
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"'{video_title}' 번역 실패: {e}")
            continue

        for code in selected_langs:
            result = translated.get(code, {})
            already_exists = code in existing_localizations
            rows.append(
                {
                    "video_id": video_id,
                    "video_title": video_title,
                    "lang_code": code,
                    "lang_name": LANGUAGE_NAME_BY_CODE.get(code, code),
                    "title": result.get("title", ""),
                    "description": result.get("description", ""),
                    "기존 번역 있음(덮어쓰기 됨)": "예" if already_exists else "아니오",
                    "등록": True,
                }
            )
        progress.progress((idx + 1) / len(selected_ids), text=f"'{video_title}' 완료")

    st.session_state.translation_rows = rows
    progress.empty()

if st.session_state.translation_rows:
    st.write("번역 결과를 확인하고 필요하면 직접 수정하세요. 이미 등록된 언어는 '기존 번역 있음' 표시가 되며, 등록을 누르면 덮어씌워집니다.")
    result_df = pd.DataFrame(st.session_state.translation_rows)
    edited_result_df = st.data_editor(
        result_df,
        column_config={
            "video_id": st.column_config.TextColumn("영상 ID", disabled=True),
            "video_title": st.column_config.TextColumn("원본 영상", disabled=True),
            "lang_code": st.column_config.TextColumn("언어 코드", disabled=True),
            "lang_name": st.column_config.TextColumn("언어", disabled=True),
            "title": st.column_config.TextColumn("번역된 제목"),
            "description": st.column_config.TextColumn("번역된 설명", width="large"),
            "기존 번역 있음(덮어쓰기 됨)": st.column_config.TextColumn("기존 번역 있음", disabled=True),
            "등록": st.column_config.CheckboxColumn("이 항목 등록"),
        },
        hide_index=True,
        use_container_width=True,
        key="result_editor",
    )

    # ── 5단계: 원본 언어(defaultLanguage) 미설정 영상 확인 ──
    videos_missing_default_lang = []
    for video_id in edited_result_df["video_id"].unique():
        details = st.session_state.video_details_cache.get(video_id, {})
        if details and not details["snippet"].get("defaultLanguage"):
            videos_missing_default_lang.append(video_id)

    default_lang_choice = {}
    if videos_missing_default_lang:
        st.warning("아래 영상은 원본 언어(defaultLanguage) 정보가 없습니다. 등록 전에 확인해주세요.")
        for video_id in videos_missing_default_lang:
            title = edited_result_df[edited_result_df["video_id"] == video_id]["video_title"].iloc[0]
            choice = st.radio(
                f"'{title}'의 원본 언어는?",
                options=[("ko", "한국어"), ("en", "영어")],
                format_func=lambda x: x[1],
                key=f"default_lang_{video_id}",
                horizontal=True,
            )
            default_lang_choice[video_id] = choice[0]

    st.divider()
    if st.button("✅ YouTube에 등록", type="primary"):
        to_register = edited_result_df[edited_result_df["등록"]]
        results = []
        for video_id in to_register["video_id"].unique():
            rows_for_video = to_register[to_register["video_id"] == video_id]
            new_localizations = {
                row["lang_code"]: {"title": row["title"], "description": row["description"]}
                for _, row in rows_for_video.iterrows()
            }
            video_title = rows_for_video["video_title"].iloc[0]
            try:
                youtube_api.upsert_localizations(
                    youtube,
                    video_id,
                    new_localizations,
                    set_default_language=default_lang_choice.get(video_id),
                )
                results.append({"영상": video_title, "상태": "✅ 성공", "내용": f"{len(new_localizations)}개 언어 등록"})
            except Exception as e:  # noqa: BLE001
                results.append({"영상": video_title, "상태": "❌ 실패", "내용": str(e)})
        st.session_state.results = results

if st.session_state.results:
    st.header("5. 등록 결과")
    st.table(pd.DataFrame(st.session_state.results))
