"""
포맷 변환 (markdown_to_html, ensure_markdown) 테스트
"""

import pytest

from utils.text_utils import markdown_to_html, ensure_markdown


class TestMarkdownToHtml:
    def test_heading_h2(self):
        result = markdown_to_html("## 소제목")
        assert "<h2>소제목</h2>" in result

    def test_heading_h3(self):
        result = markdown_to_html("### 하위 제목")
        assert "<h3>하위 제목</h3>" in result

    def test_paragraph(self):
        result = markdown_to_html("일반 텍스트입니다.")
        assert "<p>일반 텍스트입니다.</p>" in result

    def test_bold(self):
        result = markdown_to_html("이것은 **강조** 텍스트입니다.")
        assert "<strong>강조</strong>" in result

    def test_italic(self):
        result = markdown_to_html("이것은 *이탤릭* 텍스트입니다.")
        assert "<em>이탤릭</em>" in result

    def test_list(self):
        text = "- 항목 1\n- 항목 2\n- 항목 3"
        result = markdown_to_html(text)
        assert "<ul>" in result
        assert "<li>항목 1</li>" in result
        assert "</ul>" in result

    def test_hr(self):
        result = markdown_to_html("위 텍스트\n---\n아래 텍스트")
        assert "<hr>" in result

    def test_image_placeholder_preserved(self):
        result = markdown_to_html("[이미지: AI 로봇 일러스트]")
        assert "[이미지: AI 로봇 일러스트]" in result

    def test_mixed_content(self):
        text = "## 제목\n\n본문 텍스트\n\n- 리스트1\n- 리스트2\n\n마무리"
        result = markdown_to_html(text)
        assert "<h2>제목</h2>" in result
        assert "<p>본문 텍스트</p>" in result
        assert "<ul>" in result
        assert "<p>마무리</p>" in result

    def test_list_closes_before_heading(self):
        text = "- 항목\n## 제목"
        result = markdown_to_html(text)
        assert result.index("</ul>") < result.index("<h2>")


class TestEnsureMarkdown:
    def test_h1_to_h2(self):
        result = ensure_markdown("# 제목")
        assert result.startswith("## 제목")

    def test_h2_unchanged(self):
        result = ensure_markdown("## 소제목")
        assert "## 소제목" in result

    def test_normal_text_unchanged(self):
        text = "일반 텍스트입니다.\n\n## 소제목\n\n본문"
        result = ensure_markdown(text)
        assert "일반 텍스트입니다." in result
