"""
Pipeline 오케스트레이터 테스트
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from pipeline import Pipeline, PipelineResult
from utils.claude_client import ClaudeClient


def _mock_research_response():
    return json.dumps({
        "key_facts": [{"fact": "테스트 팩트", "source": "테스트", "reliability": "high"}],
        "statistics": [],
        "analogies": ["비유1"],
        "naver_angles": ["네이버 관점"],
        "tistory_angles": ["티스토리 관점"],
        "sources": [],
    })


def _mock_split_response():
    return json.dumps({
        "naver": {
            "title_candidates": ["네이버 제목"],
            "sections": [
                {"title": "섹션1", "key_points": ["포인트1"], "references": []}
            ],
            "target_length": [2000, 3000],
            "tone_notes": "강연체",
        },
        "tistory": {
            "title_candidates": ["티스토리 제목"],
            "sections": [
                {"title": "섹션1", "key_points": ["포인트1"], "references": []}
            ],
            "target_length": [3000, 4500],
            "tone_notes": "전문체",
        },
    })


def _mock_write_response(platform: str):
    if platform == "naver":
        return "AI 비서가 진화했거든요\n네이버 본문 내용이에요. 완전 다른 관점의 글이거든요."
    return "AI 기술 분석 보고서\n티스토리 본문입니다. 전문적인 분석을 제공합니다."


def _mock_edit_response():
    return "편집된 본문\n---\n수정 완료"


def _mock_quality_response():
    return json.dumps({
        "accuracy": 8, "readability": 8,
        "engagement": 8, "structure": 8, "tone": 8,
    })


def _mock_seo_response(platform: str):
    data = {
        "optimized_title": f"{platform} SEO 최적화 제목",
        "optimized_body": f"## 소제목\n\n{platform} SEO 최적화된 본문입니다.",
        "tags": ["AI", "테스트"],
        "seo_score": 8.5,
        "optimization_notes": "최적화 완료",
    }
    if platform == "tistory":
        data["meta_description"] = "메타 설명"
        data["schema_markup"] = {"@type": "BlogPosting", "headline": "제목"}
    return json.dumps(data)


def _build_side_effects():
    """전체 파이프라인 호출 순서대로 mock 응답 생성
    research(1) + split(1) + write(2) + edit(5*2) + seo(2) = 16
    """
    return [
        _mock_research_response(),
        _mock_split_response(),
        _mock_write_response("naver"),
        _mock_write_response("tistory"),
        # edit naver (5)
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_quality_response(),
        # edit tistory (5)
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_edit_response(),
        _mock_quality_response(),
        # seo (2)
        _mock_seo_response("naver"),
        _mock_seo_response("tistory"),
    ]


@pytest.fixture
def mock_claude_client():
    client = MagicMock(spec=ClaudeClient)
    client.call = AsyncMock()
    client.cost_tracker = MagicMock()
    return client


class TestPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_runs_end_to_end(self, mock_claude_client):
        """파이프라인이 끝까지 실행되는지 확인"""
        mock_claude_client.call.side_effect = _build_side_effects()

        pipe = Pipeline(mock_claude_client)
        result = await pipe.run(topic="테스트 주제", keywords=["AI", "테스트"])

        assert isinstance(result, PipelineResult)
        assert result.topic.title == "테스트 주제"
        assert result.research.topic_id == result.topic.topic_id

    @pytest.mark.asyncio
    async def test_pipeline_has_seo_results(self, mock_claude_client):
        """SEO 결과가 포함되는지 확인"""
        mock_claude_client.call.side_effect = _build_side_effects()

        pipe = Pipeline(mock_claude_client)
        result = await pipe.run(topic="테스트 주제")

        assert result.naver_seo is not None
        assert result.tistory_seo is not None
        assert result.naver_seo.platform == "naver"
        assert result.tistory_seo.platform == "tistory"
        assert result.tistory_seo.meta_description is not None

    @pytest.mark.asyncio
    async def test_pipeline_has_format_output(self, mock_claude_client):
        """포맷 변환 결과 (HTML/Markdown)가 있는지"""
        mock_claude_client.call.side_effect = _build_side_effects()

        pipe = Pipeline(mock_claude_client)
        result = await pipe.run(topic="테스트 주제")

        assert len(result.naver_html) > 0
        assert "<h2>" in result.naver_html or "<p>" in result.naver_html
        assert len(result.tistory_markdown) > 0

    @pytest.mark.asyncio
    async def test_pipeline_quality_check(self, mock_claude_client):
        """품질 검사가 정상 동작하는지"""
        mock_claude_client.call.side_effect = _build_side_effects()

        pipe = Pipeline(mock_claude_client)
        result = await pipe.run(topic="테스트 주제")

        assert result.quality_report is not None
        assert result.quality_report.naver_passed is True
        assert result.quality_report.tistory_passed is True

    @pytest.mark.asyncio
    async def test_pipeline_has_both_platforms(self, mock_claude_client):
        """네이버/티스토리 양 플랫폼 결과가 있는지"""
        mock_claude_client.call.side_effect = _build_side_effects()

        pipe = Pipeline(mock_claude_client)
        result = await pipe.run(topic="테스트 주제")

        assert result.naver_draft.platform == "naver"
        assert result.tistory_draft.platform == "tistory"
        assert result.naver_edited.platform == "naver"
        assert result.tistory_edited.platform == "tistory"
