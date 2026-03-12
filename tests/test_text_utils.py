"""
text_utils 테스트
"""

import pytest

from utils.text_utils import (
    count_chars,
    count_words,
    calculate_similarity,
    extract_image_placeholders,
    split_sentences,
    strip_html_tags,
    truncate_text,
)


class TestCountChars:
    def test_basic(self):
        assert count_chars("안녕하세요") == 5

    def test_excludes_spaces(self):
        assert count_chars("안녕 하세요") == 5

    def test_excludes_newlines(self):
        assert count_chars("안녕\n하세요") == 5

    def test_empty(self):
        assert count_chars("") == 0


class TestCountWords:
    def test_korean(self):
        assert count_words("나는 학생 입니다") == 3

    def test_english(self):
        assert count_words("hello world") == 2

    def test_mixed(self):
        assert count_words("AI는 정말 amazing 합니다") == 4

    def test_empty(self):
        assert count_words("") == 0


class TestCalculateSimilarity:
    def test_identical(self):
        assert calculate_similarity("동일한 텍스트", "동일한 텍스트") == 1.0

    def test_completely_different(self):
        result = calculate_similarity("AAAA", "ZZZZ")
        assert result < 0.3

    def test_partially_similar(self):
        result = calculate_similarity("오늘 날씨가 좋습니다", "오늘 날씨가 나쁩니다")
        assert 0.5 < result < 1.0

    def test_empty_string(self):
        assert calculate_similarity("", "텍스트") == 0.0

    def test_both_empty(self):
        assert calculate_similarity("", "") == 0.0


class TestExtractImagePlaceholders:
    def test_single(self):
        text = "본문입니다.\n[이미지: AI 로봇 일러스트]\n추가 본문."
        result = extract_image_placeholders(text)
        assert len(result) == 1
        assert result[0]["description"] == "AI 로봇 일러스트"
        assert result[0]["position"] == 2

    def test_multiple(self):
        text = "[이미지: 첫번째]\n본문\n[이미지: 두번째]"
        result = extract_image_placeholders(text)
        assert len(result) == 2

    def test_no_images(self):
        assert extract_image_placeholders("이미지가 없는 본문") == []

    def test_colon_spacing(self):
        text = "[이미지:설명 없이 붙여쓴 경우]"
        result = extract_image_placeholders(text)
        assert len(result) == 1


class TestSplitSentences:
    def test_basic(self):
        result = split_sentences("첫 문장입니다. 두 번째 문장이에요. 세 번째요.")
        assert len(result) == 3

    def test_question_mark(self):
        result = split_sentences("이게 뭘까요? 그렇거든요.")
        assert len(result) == 2

    def test_exclamation(self):
        result = split_sentences("대단해요! 정말이에요.")
        assert len(result) == 2

    def test_single_sentence(self):
        result = split_sentences("하나의 문장")
        assert len(result) == 1


class TestStripHtmlTags:
    def test_basic(self):
        assert strip_html_tags("<p>텍스트</p>") == "텍스트"

    def test_nested(self):
        assert strip_html_tags("<div><b>굵은</b> 글씨</div>") == "굵은 글씨"

    def test_no_tags(self):
        assert strip_html_tags("순수 텍스트") == "순수 텍스트"

    def test_attributes(self):
        result = strip_html_tags('<a href="url">링크</a>')
        assert result == "링크"


class TestTruncateText:
    def test_short_text(self):
        assert truncate_text("짧은 글", 10) == "짧은 글"

    def test_exact_length(self):
        assert truncate_text("12345", 5) == "12345"

    def test_truncated(self):
        result = truncate_text("이것은 긴 텍스트입니다", 8)
        assert len(result) == 8
        assert result.endswith("...")

    def test_custom_suffix(self):
        result = truncate_text("이것은 긴 텍스트입니다", 8, suffix="…")
        assert result.endswith("…")
