"""
ResearchAgent 테스트
"""

import json

import pytest

from agents.research_agent import ResearchAgent
from agents.data_models import TopicPackage, ResearchNote


@pytest.fixture
def researcher(mock_claude_client):
    return ResearchAgent(mock_claude_client)


@pytest.fixture
def sample_topic():
    return TopicPackage(
        topic_id="test_001",
        title="GPT-5 출시 소식",
        keywords=["GPT-5", "OpenAI"],
        category="ai_products",
        content_type="news_briefing",
        source="OpenAI Blog",
        source_url="https://openai.com/blog/gpt5",
        curator_score=9.0,
    )


@pytest.fixture
def mock_research_response():
    return json.dumps({
        "key_facts": [
            {"fact": "GPT-5가 2025년에 출시되었다", "source": "OpenAI", "reliability": "high"},
            {"fact": "멀티모달 성능이 크게 향상되었다", "source": "벤치마크 결과", "reliability": "high"},
        ],
        "statistics": [
            {"stat": "GPT-5는 MMLU 벤치마크에서 95% 달성", "source": "OpenAI 발표"},
        ],
        "analogies": ["스마트폰이 피처폰을 대체한 것처럼", "AI 비서가 인턴 직원 같은 역할"],
        "naver_angles": ["GPT-5로 할 수 있는 신기한 것들", "무료로 써볼 수 있을까?"],
        "tistory_angles": ["GPT-5의 아키텍처 변경 분석", "기업 도입 시 고려사항"],
        "sources": ["https://openai.com/blog/gpt5"],
    })


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_research_returns_note(
        self, researcher, sample_topic, mock_research_response
    ):
        """research()가 ResearchNote를 반환하는지 확인"""
        researcher.claude.call.return_value = mock_research_response

        result = await researcher.research(sample_topic)

        assert isinstance(result, ResearchNote)
        assert result.topic_id == "test_001"

    @pytest.mark.asyncio
    async def test_key_facts_parsed(
        self, researcher, sample_topic, mock_research_response
    ):
        """핵심 팩트가 파싱되는지 확인"""
        researcher.claude.call.return_value = mock_research_response

        result = await researcher.research(sample_topic)

        assert len(result.key_facts) == 2
        assert result.key_facts[0]["reliability"] == "high"

    @pytest.mark.asyncio
    async def test_platform_angles(
        self, researcher, sample_topic, mock_research_response
    ):
        """플랫폼별 관점이 파싱되는지 확인"""
        researcher.claude.call.return_value = mock_research_response

        result = await researcher.research(sample_topic)

        assert len(result.naver_angles) == 2
        assert len(result.tistory_angles) == 2

    @pytest.mark.asyncio
    async def test_analogies_parsed(
        self, researcher, sample_topic, mock_research_response
    ):
        """비유 소재가 파싱되는지 확인"""
        researcher.claude.call.return_value = mock_research_response

        result = await researcher.research(sample_topic)

        assert len(result.analogies) == 2

    @pytest.mark.asyncio
    async def test_json_in_code_block(
        self, researcher, sample_topic, mock_research_response
    ):
        """```json 코드 블록 내 JSON 파싱"""
        wrapped = f"```json\n{mock_research_response}\n```"
        researcher.claude.call.return_value = wrapped

        result = await researcher.research(sample_topic)

        assert isinstance(result, ResearchNote)
        assert len(result.key_facts) == 2
