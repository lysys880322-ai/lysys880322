# YouTube Data API v3 래퍼 — 목록 조회는 검색(search.list, 100유닛)이 아니라 내 채널의
# "업로드 재생목록"을 playlistItems.list(1유닛)로 읽어서 쿼터를 아낀다. 실제 제목/설명/
# 언어/기존 번역은 videos.list(part=snippet,localizations)로 한 번에 가져온다.
#
# videos.update는 part에 넣은 최상위 리소스(snippet 등)를 요청 본문 내용으로 통째로
# 대체하는 API라서, 반드시 "최신 snippet+localizations를 먼저 조회 → 필요한 부분만 바꿔
# 병합 → 그대로 다시 전송" 순서를 지켜야 기존 정보(카테고리, 태그 등)가 사라지지 않는다.
from typing import Optional


def get_uploads_playlist_id(youtube) -> str:
    resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("내 채널 정보를 찾을 수 없습니다. 로그인한 계정에 YouTube 채널이 있는지 확인하세요.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def list_my_videos(youtube, max_total: int = 200) -> list[dict]:
    """내 채널에 올라온 영상 목록(영상ID, 제목, 썸네일)을 최근 업로드 순으로 가져온다."""
    playlist_id = get_uploads_playlist_id(youtube)
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
    snippet = dict(current["snippet"])
    merged_localizations = {**current["localizations"], **new_localizations}

    if set_default_language and not snippet.get("defaultLanguage"):
        snippet["defaultLanguage"] = set_default_language

    body = {"id": video_id, "snippet": snippet, "localizations": merged_localizations}
    result = youtube.videos().update(part="snippet,localizations", body=body).execute()
    return result
