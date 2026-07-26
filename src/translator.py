# Gemini API로 제목·설명을 번역한다. 영상 1개당 언어별로 따로 호출하지 않고, 선택한
# 언어를 한 번의 요청에 묶어서 보낸다 — API 호출 횟수(무료 티어 분당 요청 제한)를 아끼기 위해서다.
#
# 예전 google-generativeai 패키지는 지원이 완전히 종료되어(deprecated), 현재 구글이
# 공식적으로 유지하는 google-genai(신규 통합 SDK) 패키지를 사용한다.
import json
import re

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, GEMINI_MODEL, LANGUAGE_ENGLISH_BY_CODE

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(".env에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _extract_json(text: str) -> dict:
    text = text.strip()
    # 모델이 ```json ... ``` 코드블록으로 감싸서 답하는 경우를 대비한 방어 처리.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"번역 결과에서 JSON을 찾지 못했습니다: {text[:200]}")
    return json.loads(match.group(0))


def translate_title_and_description(
    title: str,
    description: str,
    target_lang_codes: list[str],
) -> dict[str, dict]:
    """반환값 예: {"en": {"title": "...", "description": "..."}, "ja": {...}}"""
    client = _get_client()
    if not target_lang_codes:
        return {}

    lang_list_text = "\n".join(f'- 언어 코드 "{code}": {LANGUAGE_ENGLISH_BY_CODE[code]}' for code in target_lang_codes)

    prompt = f"""너는 유튜브 음악 플레이리스트 채널의 다국어 현지화 전문가야.
아래 원본 제목과 설명을, 지정된 각 언어로 번역해줘.

절대 규칙:
- 직역하지 말고, 그 나라 사람이 실제로 유튜브에서 검색할 때 쓸 법한 자연스러운 표현과 키워드로 의역할 것
- 음악/플레이리스트 채널 특유의 톤(감성적이고 매력적인 느낌)을 유지할 것
- 원본에 없는 내용을 지어내지 말 것
- 각 언어의 실제 원어(해당 언어 문자)로 작성할 것

원본 제목:
{title}

원본 설명:
{description}

번역할 언어 목록:
{lang_list_text}

아래 JSON 형식으로만 답해. 다른 설명 문장은 절대 붙이지 마:
{{
  "언어코드": {{"title": "번역된 제목", "description": "번역된 설명"}},
  ...
}}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4,
        ),
    )
    return _extract_json(response.text)
