"""
ContentSplitter 에이전트 테스트
"""

import json

import pytest

from agents.content_splitter import ContentSplitter
from agents.data_models import TopicPackage, ResearchNote, SplitOutlines


@pytest.fixture
def splitter(mock_claude_client):
    """ContentSplitter 인스턴스 (mock Claude)"""
    return ContentSplitter(mock_claude_client)


@pytest.fixture
def sample_topic():
    return TopicPackage(
        topic_id="test_001",
        title="Claude 4 출시와 AI 에이전트의 미래",
        keywords=["Claude", "AI 에이전트", "Anthropic"],
        category="ai_products",
        content_type="news_briefing",
        source="Anthropic News",
        curator_score=8.5,
    )


@pytest.fixture
def sample_research():
    return ResearchNote(
        topic_id="test_001",
        key_facts=[
            {"fact": "Claude 4가 2025년에 출시되었다", "source": "Anthropic", "reliability": "high"}
        ],
        statistics=[
            {"stat": "Claude 사용자 1억 명 돌파", "source": "Anthropic 공식 발표"}
        ],
        analogies=["비서를 고용하는 것과 비슷"],
        naver_angles=["일반인이 Claude로 할 수 있는 일"],
        tistory_angles=["Claude 4의 기술적 개선 사항 분석"],
        sources=["https://anthropic.com/news"],
    )


@pytest.fixture
def mock_split_response():
    """Claude가 반환할 JSON 응답 목"""
    return json.dumps({
        "naver": {
            "title_candidates": [
                "Claude 4, AI 비서가 한 단계 더 똑똑해졌거든요",
                "AI 비서 Claude 새 버전 나왔는데 뭐가 달라졌을까?",
                "Claude 4 출시! 누구나 쓸 수 있는 AI 비서의 진화"
            ],
            "sections": [
                {
                    "title": "Claude 4가 뭔데?",
                    "key_points": ["AI 비서 서비스", "일반인도 쉽게 사용"],
                    "references": []
                },
                {
                    "title": "뭐가 달라졌을까?",
                    "key_points": ["더 자연스러운 대화", "실수가 줄었다"],
                    "references": []
                },
                {
                    "title": "나도 써볼 수 있을까?",
                    "key_points": ["무료 사용법", "활용 팁"],
                    "references": []
                }
            ],
            "target_length": [2000, 3000],
            "tone_notes": "설민석 강연체, ~거든요 체"
        },
        "tistory": {
            "title_candidates": [
                "Claude 4 출시: AI 에이전트 시대의 본격적인 시작",
                "Anthropic Claude 4 심층 분석 — 달라진 점과 실무 적용",
                "Claude 4 vs GPT-5: 차세대 LLM 비교 분석"
            ],
            "sections": [
                {
                    "title": "Claude 4 개요 및 주요 변경사항",
                    "key_points": ["모델 아키텍처 개선", "컨텍스트 윈도우 확대"],
                    "references": ["Anthropic 공식 발표"]
                },
                {
                    "title": "성능 벤치마크 비교",
                    "key_points": ["MMLU 점수", "코딩 벤치마크"],
                    "references": []
                },
                {
                    "title": "실무 도입 시 고려사항",
                    "key_points": ["API 가격 변동", "기존 워크플로우 마이그레이션"],
                    "references": []
                }
            ],
            "target_length": [3000, 4500],
            "tone_notes": "전문 리뷰어 톤, ~입니다 체"
        }
    })


class TestContentSplitter:
    @pytest.mark.asyncio
    async def test_split_returns_split_outlines(
        self, splitter, sample_topic, sample_research, mock_split_response
    ):
        """split()이 SplitOutlines를 반환하는지 확인"""
        splitter.claude.call.return_value = mock_split_response

        result = await splitter.split(sample_topic, sample_research)

        assert isinstance(result, SplitOutlines)
        assert result.topic_id == "test_001"

    @pytest.mark.asyncio
    async def test_naver_outline_structure(
        self, splitter, sample_topic, sample_research, mock_split_response
    ):
        """네이버 아웃라인 구조 확인"""
        splitter.claude.call.return_value = mock_split_response

        result = await splitter.split(sample_topic, sample_research)

        assert len(result.naver.title_candidates) == 3
        assert len(result.naver.sections) == 3
        assert result.naver.target_length == (2000, 3000)

    @pytest.mark.asyncio
    async def test_tistory_outline_structure(
        self, splitter, sample_topic, sample_research, mock_split_response
    ):
        """티스토리 아웃라인 구조 확인"""
        splitter.claude.call.return_value = mock_split_response

        result = await splitter.split(sample_topic, sample_research)

        assert len(result.tistory.title_candidates) == 3
        assert len(result.tistory.sections) == 3
        assert result.tistory.target_length == (3000, 4500)

    @pytest.mark.asyncio
    async def test_claude_call_invoked(
        self, splitter, sample_topic, sample_research, mock_split_response
    ):
        """Claude API가 호출되었는지 확인"""
        splitter.claude.call.return_value = mock_split_response

        await splitter.split(sample_topic, sample_research)

        splitter.claude.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_json_in_code_block(
        self, splitter, sample_topic, sample_research, mock_split_response
    ):
        """```json 코드 블록 내 JSON 파싱"""
        wrapped = f"```json\n{mock_split_response}\n```"
        splitter.claude.call.return_value = wrapped

        result = await splitter.split(sample_topic, sample_research)

        assert isinstance(result, SplitOutlines)
