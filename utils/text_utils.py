"""
텍스트 처리 유틸리티
여러 에이전트가 공통으로 사용하는 텍스트 관련 함수를 제공합니다.
"""

import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from io import StringIO


def count_chars(text: str) -> int:
    """공백 제외 글자 수 카운트

    Args:
        text: 대상 텍스트

    Returns:
        공백을 제외한 글자 수
    """
    return len(text.replace(" ", "").replace("\n", "").replace("\t", ""))


def count_words(text: str) -> int:
    """단어 수 카운트 (한국어+영어 혼합 대응)

    Args:
        text: 대상 텍스트

    Returns:
        단어 수
    """
    return len(text.split())


def calculate_similarity(text1: str, text2: str) -> float:
    """두 텍스트 간 유사도 측정

    Args:
        text1: 비교 텍스트 1
        text2: 비교 텍스트 2

    Returns:
        유사도 (0.0 ~ 1.0)
    """
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def extract_image_placeholders(text: str) -> list[dict]:
    """[이미지: 설명] 패턴을 추출

    Args:
        text: 이미지 마커가 포함된 텍스트

    Returns:
        [{"position": 줄번호, "description": "설명"}] 리스트
    """
    pattern = re.compile(r"\[이미지:\s*(.+?)\]")
    results = []
    for i, line in enumerate(text.split("\n"), start=1):
        match = pattern.search(line)
        if match:
            results.append({
                "position": i,
                "description": match.group(1).strip(),
            })
    return results


def split_sentences(text: str) -> list[str]:
    """한국어 문장 분리

    마침표, 물음표, 느낌표 기준으로 분리합니다.
    괄호 안이나 인용문 내부의 구두점은 무시합니다.

    Args:
        text: 분리할 텍스트

    Returns:
        문장 리스트
    """
    pattern = re.compile(r"(?<=[.?!])\s+")
    raw = pattern.split(text.strip())
    return [s.strip() for s in raw if s.strip()]


class _HTMLStripper(HTMLParser):
    """HTML 태그 제거용 내부 파서"""

    def __init__(self):
        super().__init__()
        self._fed: list[str] = []

    def handle_data(self, data: str) -> None:
        self._fed.append(data)

    def get_text(self) -> str:
        return "".join(self._fed)


def strip_html_tags(text: str) -> str:
    """HTML 태그 제거

    Args:
        text: HTML이 포함된 텍스트

    Returns:
        태그가 제거된 순수 텍스트
    """
    stripper = _HTMLStripper()
    stripper.feed(text)
    return stripper.get_text()


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """지정 길이로 텍스트 자르기

    Args:
        text: 대상 텍스트
        max_length: 최대 글자 수 (suffix 포함)
        suffix: 잘린 경우 뒤에 붙일 문자열

    Returns:
        잘린 텍스트
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


# ── 포맷 변환 ──


def markdown_to_html(text: str) -> str:
    """Markdown을 네이버 블로그용 HTML로 변환

    지원: 헤딩(##), 볼드(**), 이탤릭(*), 리스트(-), 구분선(---),
    이미지 플레이스홀더([이미지:]), 문단 분리

    Args:
        text: Markdown 텍스트

    Returns:
        HTML 변환된 텍스트
    """
    lines = text.split("\n")
    html_lines: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # 빈 줄
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("")
            continue

        # 구분선
        if stripped == "---":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
            continue

        # 헤딩
        if stripped.startswith("###"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            content = stripped.lstrip("#").strip()
            html_lines.append(f"<h3>{content}</h3>")
            continue
        if stripped.startswith("##"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            content = stripped.lstrip("#").strip()
            html_lines.append(f"<h2>{content}</h2>")
            continue

        # 리스트
        if stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = stripped[2:]
            content = _inline_markdown(content)
            html_lines.append(f"  <li>{content}</li>")
            continue

        # 리스트 종료 후 일반 문단
        if in_list:
            html_lines.append("</ul>")
            in_list = False

        # 이미지 플레이스홀더 유지
        if "[이미지:" in stripped:
            html_lines.append(f"<p>{stripped}</p>")
            continue

        # 일반 문단
        content = _inline_markdown(stripped)
        html_lines.append(f"<p>{content}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def _inline_markdown(text: str) -> str:
    """인라인 Markdown 변환 (볼드, 이탤릭)"""
    # 볼드 (**text**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # 이탤릭 (*text*)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def ensure_markdown(text: str) -> str:
    """티스토리용 Markdown 정리

    이미 Markdown 형식인 글의 구조를 정리합니다.
    - 헤딩 레벨 통일 (H2부터 시작)
    - 빈 줄 정리
    - 이미지 플레이스홀더 유지

    Args:
        text: Markdown 텍스트

    Returns:
        정리된 Markdown 텍스트
    """
    lines = text.split("\n")
    result: list[str] = []

    for line in lines:
        stripped = line.strip()

        # H1(#)을 H2(##)로 변환 (블로그에서 H1은 제목에 사용)
        if stripped.startswith("# ") and not stripped.startswith("##"):
            result.append(f"#{stripped}")
            continue

        result.append(line)

    return "\n".join(result)
