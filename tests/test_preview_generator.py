"""
미리보기 생성기 테스트
"""

import pytest
from unittest.mock import MagicMock

from approval.preview_generator import PreviewGenerator


@pytest.fixture
def generator():
    return PreviewGenerator()


@pytest.fixture
def mock_result():
    result = MagicMock()
    result.topic.title = "AI 테스트 주제"
    result.topic.category = "ai_products"
    result.topic.content_type = "news_briefing"
    result.naver_edited.final_draft = "네이버 본문 내용"
    result.naver_edited.quality_score = 8.5
    result.tistory_edited.final_draft = "티스토리 본문 내용"
    result.tistory_edited.quality_score = 7.0
    result.naver_seo.title_final = "네이버 SEO 제목"
    result.naver_seo.seo_score = 8.0
    result.tistory_seo.title_final = "티스토리 SEO 제목"
    result.tistory_seo.seo_score = 7.5
    result.quality_report.similarity = 0.35
    result.quality_report.issues = []
    return result


class TestPreviewGenerator:
    def test_generate_contains_topic(self, generator, mock_result):
        """미리보기에 주제 정보가 포함되는지"""
        preview = generator.generate(mock_result)

        assert "AI 테스트 주제" in preview
        assert "ai_products" in preview

    def test_generate_contains_scores(self, generator, mock_result):
        """미리보기에 품질 점수가 포함되는지"""
        preview = generator.generate(mock_result)

        assert "8.5" in preview
        assert "7.0" in preview

    def test_generate_green_emoji_for_high_score(self, generator, mock_result):
        """높은 점수에 녹색 이모지"""
        preview = generator.generate(mock_result)
        assert "🟢" in preview  # 8.5 >= 8.5

    def test_generate_red_emoji_for_low_score(self, generator, mock_result):
        """낮은 점수에 빨간 이모지"""
        preview = generator.generate(mock_result)
        assert "🔴" in preview  # 7.0 < 7.5

    def test_generate_shows_issues(self, generator, mock_result):
        """이슈가 있으면 표시되는지"""
        mock_result.quality_report.issues = ["품질 미달", "유사도 초과"]

        preview = generator.generate(mock_result)

        assert "품질 미달" in preview
        assert "유사도 초과" in preview

    def test_generate_seo_titles(self, generator, mock_result):
        """SEO 제목이 미리보기에 포함되는지"""
        preview = generator.generate(mock_result)

        assert "네이버 SEO 제목" in preview
        assert "티스토리 SEO 제목" in preview

    def test_generate_similarity(self, generator, mock_result):
        """유사도가 표시되는지"""
        preview = generator.generate(mock_result)
        assert "35" in preview  # 0.35 -> 35%
