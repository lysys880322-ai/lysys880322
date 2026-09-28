# YouTube Data API v3 래퍼 — 목록 조회는 검색(search.list, 100유닛)이 아니라 내 채널의
# "업로드 재생목록"을 playlistItems.list(1유닛)로 읽어서 쿼터를 아낀다. 실제 제목/설명/
# 언어/기존 번역은 videos.list(part=snippet,localizations)로 한 번에 가져온다.
#
# videos.update는 part에 넣은 최상위 리소스(snippet 등)를 요청 본문 내용으로 통째로
# 대체하는 API라서, 반드시 "최신 snippet+localizations를 먼저 조회 → 필요한 부분만 바꿔
# 병합 → 그대로 다시 전송" 순서를 지켜야 기존 정보(카테고리, 태그 등)가 사라지지 않는다.
import re
from typing import Optional

from googleapiclient.errors import HttpError

TITLE_MAX_LEN = 100
# 유튜브 설명 제한은 5000바이트라, 한글처럼 1글자가 여러 바이트인 경우를 감안해 여유있게 자른다.
DESCRIPTION_MAX_BYTES = 4800


def _truncate_title(title: str) -> str:
    return title if len(title) <= TITLE_MAX_LEN else title[: TITLE_MAX_LEN - 1] + "…"


def _truncate_description(description: str) -> str:
    encoded = description.encode("utf-8")
    if len(encoded) <= DESCRIPTION_MAX_BYTES:
        return description
    return encoded[:DESCRIPTION_MAX_BYTES].decode("utf-8", errors="ignore")


_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def extract_video_id(text: str) -> Optional[str]:
    """유튜브 영상 링크(여러 형태) 또는 11자리 영상 ID 그 자체에서 영상 ID만 뽑아낸다.
    "채널 목록 자동 불러오기"가 계정 문제로 안 될 때, 영상 링크·ID를 직접 붙여넣어 우회하는
    기능(2026-09)에서 쓴다. 못 알아보면 None."""
    if not text:
        return None
    text = text.strip()
    m = _VIDEO_ID_RE.search(text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    return None


def get_channel_id_by_handle(youtube, handle: str) -> str:
    """@핸들(또는 채널 URL에서 뽑은 핸들)로 채널 고유 ID를 찾는다. "mine=True"(로그인
    세션이 어느 채널로 인증됐는지)와 달리, 이건 항상 그 핸들이 가리키는 정확한 채널을
    가리켜서 로그인 계정의 "활성 채널" 혼선과 무관하게 동작한다(2026-09, mine=True가
    엉뚱한 빈 채널로 붙는 문제의 우회책). 공개 채널 정보 조회라 로그인 없이도 되지만,
    비공개(미공개) 영상까지 보려면 그 채널 관리 권한이 있는 계정으로 로그인은 돼있어야 한다."""
    handle = handle.strip().lstrip("@")
    resp = youtube.channels().list(part="contentDetails,snippet", forHandle=f"@{handle}").execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError(f"'@{handle}' 핸들의 채널을 찾을 수 없습니다. 핸들 철자를 확인해주세요.")
    return items[0]


def get_uploads_playlist_id(youtube) -> str:
    resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("내 채널 정보를 찾을 수 없습니다. 로그인한 계정에 YouTube 채널이 있는지 확인하세요.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _list_videos_in_playlist(youtube, playlist_id: str, max_total: int = 200) -> list[dict]:
    videos: list[dict] = []
    page_token: Optional[str] = None

    while len(videos) < max_total:
        resp = (
            youtube.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, max_total - len(videos)),
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("items", []):
            snippet = item["snippet"]
            videos.append(
                {
                    "video_id": item["contentDetails"]["videoId"],
                    "title": snippet.get("title", ""),
                    "thumbnail": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
                }
            )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return videos


def list_my_videos(youtube, max_total: int = 200) -> list[dict]:
    """내 채널에 올라온 영상 목록(영상ID, 제목, 썸네일)을 최근 업로드 순으로 가져온다."""
    playlist_id = get_uploads_playlist_id(youtube)
    return _list_videos_in_playlist(youtube, playlist_id, max_total)


def list_videos_by_handle(youtube, handle: str, max_total: int = 200) -> tuple[str, list[dict]]:
    """@핸들로 지정한 채널의 영상 목록을 가져온다. mine=True가 엉뚱한 채널로 붙는 문제의
    우회책(2026-09) — 반환값은 (채널 이름, 영상 목록). 공개된 영상만 나온다(비공개·미등록
    영상은 채널 소유자 권한으로 봐도 이 방식으로는 안 보일 수 있음 — 그럴 땐 영상 링크를
    직접 추가하는 기능을 쓴다)."""
    channel = get_channel_id_by_handle(youtube, handle)
    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    channel_title = channel["snippet"]["title"]
    return channel_title, _list_videos_in_playlist(youtube, playlist_id, max_total)


def get_video_full_details(youtube, video_id: str) -> dict:
    """지금 시점의 snippet 전체와 기존 localizations 전체를 그대로 가져온다.
    이후 업데이트 시 이 값을 기반으로 병합해야 기존 정보가 안전하게 보존된다."""
    resp = youtube.videos().list(part="snippet,localizations", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError(f"영상을 찾을 수 없습니다: {video_id}")
    item = items[0]
    return {
        "video_id": video_id,
        "snippet": item["snippet"],
        "localizations": item.get("localizations", {}) or {},
    }


def upsert_localizations(
    youtube,
    video_id: str,
    new_localizations: dict[str, dict],
    set_default_language: Optional[str] = None,
) -> dict:
    """선택한 언어의 번역만 추가/갱신하고, 이미 있던 다른 언어 번역과 원본 snippet 항목
    (카테고리·태그 등)은 그대로 보존한 채로 videos.update를 호출한다."""
    current = get_video_full_details(youtube, video_id)
    full_snippet = current["snippet"]

    # 번역된 제목/설명이 유튜브 제한(제목 100자, 설명 5000바이트)을 넘으면 요청 전체가
    # "invalidVideoMetadata"로 거부되므로, 넘는 경우 안전하게 잘라서 보낸다.
    safe_new_localizations = {
        lang: {
            "title": _truncate_title(loc.get("title", "")),
            "description": _truncate_description(loc.get("description", "")),
        }
        for lang, loc in new_localizations.items()
    }
    merged_localizations = {**current["localizations"], **safe_new_localizations}

    # videos.list가 돌려주는 snippet에는 channelId/publishedAt/thumbnails/localized 같은
    # 읽기 전용 항목이 섞여 있는데, 그걸 그대로 videos.update에 다시 보내면 유튜브가
    # "invalidVideoMetadata"로 요청 전체를 거부한다. 실제로 수정 가능한 항목만 추려서 보낸다.
    snippet = {
        "title": full_snippet.get("title", ""),
        "description": full_snippet.get("description", ""),
        "categoryId": full_snippet.get("categoryId"),
    }
    if "tags" in full_snippet:
        snippet["tags"] = full_snippet["tags"]
    if full_snippet.get("defaultLanguage"):
        snippet["defaultLanguage"] = full_snippet["defaultLanguage"]
    if full_snippet.get("defaultAudioLanguage"):
        snippet["defaultAudioLanguage"] = full_snippet["defaultAudioLanguage"]

    if set_default_language and not snippet.get("defaultLanguage"):
        snippet["defaultLanguage"] = set_default_language

    body = {"id": video_id, "snippet": snippet, "localizations": merged_localizations}
    try:
        result = youtube.videos().update(part="snippet,localizations", body=body).execute()
    except HttpError as e:
        title_lengths = {lang: len(loc["title"]) for lang, loc in merged_localizations.items()}
        raise RuntimeError(
            f"{e}\n[디버그] categoryId={snippet.get('categoryId')!r}, "
            f"defaultLanguage={snippet.get('defaultLanguage')!r}, 언어별 제목 길이={title_lengths}"
        ) from e
    return result
