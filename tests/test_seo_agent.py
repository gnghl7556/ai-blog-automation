"""
SEOAgent 테스트
"""

import json

import pytest

from agents.seo_agent import SEOAgent
from agents.data_models import EditResult, SEOResult


@pytest.fixture
def seo_agent(mock_claude_client):
    return SEOAgent(mock_claude_client)


@pytest.fixture
def naver_edit_result():
    return EditResult(
        content_id="naver_test_001",
        platform="naver",
        final_draft="네이버 본문입니다. ChatGPT 사용법을 알려드릴게요.",
        quality_score=8.0,
        quality_detail={"accuracy": 8, "readability": 8, "engagement": 8, "structure": 8, "tone": 8},
        edit_summary={},
        passed=True,
    )


@pytest.fixture
def tistory_edit_result():
    return EditResult(
        content_id="tistory_test_001",
        platform="tistory",
        final_draft="티스토리 본문입니다. Claude 4의 성능을 분석합니다.",
        quality_score=8.5,
        quality_detail={"accuracy": 9, "readability": 8, "engagement": 8, "structure": 9, "tone": 8},
        edit_summary={},
        passed=True,
    )


def mock_naver_seo_response():
    return json.dumps({
        "optimized_title": "ChatGPT 무료 사용법 총정리 (2025년 최신)",
        "optimized_body": "최적화된 네이버 본문입니다.",
        "tags": ["ChatGPT", "ChatGPT 사용법", "AI 챗봇", "GPT 무료"],
        "seo_score": 8.5,
        "optimization_notes": "제목에 핵심 키워드 배치, 태그 최적화",
    })


def mock_tistory_seo_response():
    return json.dumps({
        "optimized_title": "Claude 4 vs GPT-5 성능 비교 분석 — 2025년 최신",
        "optimized_body": "## Claude 4 개요\n\n최적화된 티스토리 본문입니다.",
        "tags": ["Claude 4", "GPT-5", "LLM 비교"],
        "meta_description": "Claude 4와 GPT-5의 벤치마크 성능을 비교 분석합니다.",
        "schema_markup": {
            "@type": "BlogPosting",
            "headline": "Claude 4 vs GPT-5 성능 비교",
            "description": "비교 분석",
        },
        "seo_score": 9.0,
        "optimization_notes": "메타 태그 추가, 구조화 데이터 생성",
    })


class TestSEOAgent:
    @pytest.mark.asyncio
    async def test_naver_seo(self, seo_agent, naver_edit_result):
        """네이버 SEO 최적화 결과 확인"""
        seo_agent.claude.call.return_value = mock_naver_seo_response()

        result = await seo_agent.optimize(naver_edit_result, ["ChatGPT", "AI"])

        assert isinstance(result, SEOResult)
        assert result.platform == "naver"
        assert "ChatGPT" in result.title_final
        assert len(result.tags) >= 3
        assert result.seo_score == 8.5
        assert result.meta_description is None

    @pytest.mark.asyncio
    async def test_tistory_seo(self, seo_agent, tistory_edit_result):
        """티스토리 SEO 최적화 결과 확인 (메타 태그 포함)"""
        seo_agent.claude.call.return_value = mock_tistory_seo_response()

        result = await seo_agent.optimize(tistory_edit_result, ["Claude", "GPT-5"])

        assert isinstance(result, SEOResult)
        assert result.platform == "tistory"
        assert result.meta_description is not None
        assert result.schema_markup is not None
        assert result.schema_markup["@type"] == "BlogPosting"

    @pytest.mark.asyncio
    async def test_seo_score_parsed(self, seo_agent, naver_edit_result):
        """SEO 점수가 float로 파싱되는지"""
        seo_agent.claude.call.return_value = mock_naver_seo_response()

        result = await seo_agent.optimize(naver_edit_result, ["AI"])

        assert isinstance(result.seo_score, float)

    @pytest.mark.asyncio
    async def test_json_in_code_block(self, seo_agent, naver_edit_result):
        """```json 코드 블록 내 JSON 파싱"""
        wrapped = f"```json\n{mock_naver_seo_response()}\n```"
        seo_agent.claude.call.return_value = wrapped

        result = await seo_agent.optimize(naver_edit_result, ["AI"])

        assert isinstance(result, SEOResult)
