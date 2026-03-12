"""
WritingAgent 테스트
"""

import pytest

from agents.writing_agent import WritingAgent
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    PlatformOutline,
    SectionOutline,
    PlatformDraft,
)


@pytest.fixture
def writer(mock_claude_client):
    """WritingAgent 인스턴스 (mock Claude)"""
    return WritingAgent(mock_claude_client)


@pytest.fixture
def sample_topic():
    return TopicPackage(
        topic_id="test_001",
        title="Claude 4 출시",
        keywords=["Claude", "AI"],
        category="ai_products",
        content_type="news_briefing",
        source="Anthropic",
        curator_score=8.5,
    )


@pytest.fixture
def sample_research():
    return ResearchNote(
        topic_id="test_001",
        key_facts=[{"fact": "Claude 4 출시", "source": "Anthropic", "reliability": "high"}],
        naver_angles=["일반인 활용법"],
        tistory_angles=["기술 분석"],
    )


@pytest.fixture
def sample_outline():
    return PlatformOutline(
        title_candidates=["제목 후보 1", "제목 후보 2", "제목 후보 3"],
        sections=[
            SectionOutline(title="도입", key_points=["포인트1"]),
            SectionOutline(title="본론", key_points=["포인트2"]),
            SectionOutline(title="마무리", key_points=["포인트3"]),
        ],
        target_length=(2000, 3000),
        tone_notes="테스트 톤",
    )


MOCK_NAVER_RESPONSE = """AI 비서 Claude가 한 단계 더 진화했거든요
얼마 전에 친구가 저한테 이러더라고요. "AI 비서 써봤어?" 하고요.

[이미지: Claude 4 소개 화면]

사실 저도 처음엔 반신반의했거든요. 근데 직접 써보니까 확실히 달라졌어요.

## Claude 4가 뭔데?

쉽게 말하면 AI 비서 서비스인 거예요.

[이미지: AI 비서 활용 예시]

## 뭐가 달라졌을까?

가장 큰 변화는 대화가 훨씬 자연스러워졌다는 거거든요.

[이미지: 이전 버전과 비교]"""

MOCK_TISTORY_RESPONSE = """Claude 4 출시: AI 에이전트 시대의 본격적인 시작
Anthropic이 Claude 4를 공식 발표했습니다.

[이미지: Claude 4 아키텍처 다이어그램]

## Claude 4 개요

Claude 4는 이전 모델 대비 상당한 성능 향상을 보여줍니다.

[이미지: 벤치마크 비교 차트]

## 주요 변경사항

컨텍스트 윈도우(Context Window)가 대폭 확대되었습니다."""


class TestWritingAgent:
    @pytest.mark.asyncio
    async def test_write_naver(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """네이버 글 작성 결과 확인"""
        writer.claude.call.return_value = MOCK_NAVER_RESPONSE

        result = await writer.write(
            sample_outline, "naver", sample_topic, sample_research
        )

        assert isinstance(result, PlatformDraft)
        assert result.platform == "naver"
        assert result.topic_id == "test_001"
        assert "naver" in result.content_id
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_write_tistory(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """티스토리 글 작성 결과 확인"""
        writer.claude.call.return_value = MOCK_TISTORY_RESPONSE

        result = await writer.write(
            sample_outline, "tistory", sample_topic, sample_research
        )

        assert isinstance(result, PlatformDraft)
        assert result.platform == "tistory"

    @pytest.mark.asyncio
    async def test_image_placeholders_extracted(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """이미지 플레이스홀더 추출 확인"""
        writer.claude.call.return_value = MOCK_NAVER_RESPONSE

        result = await writer.write(
            sample_outline, "naver", sample_topic, sample_research
        )

        assert len(result.image_placeholders) == 3

    @pytest.mark.asyncio
    async def test_title_extracted(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """제목 추출 확인"""
        writer.claude.call.return_value = MOCK_NAVER_RESPONSE

        result = await writer.write(
            sample_outline, "naver", sample_topic, sample_research
        )

        assert "Claude" in result.title

    @pytest.mark.asyncio
    async def test_invalid_platform_raises(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """잘못된 플랫폼 지정 시 에러"""
        from agents.base_agent import AgentError

        with pytest.raises(AgentError):
            await writer.write(
                sample_outline, "invalid", sample_topic, sample_research
            )

    @pytest.mark.asyncio
    async def test_persona_loaded(
        self, writer, sample_outline, sample_topic, sample_research
    ):
        """페르소나 프롬프트가 system으로 전달되는지 확인"""
        writer.claude.call.return_value = MOCK_NAVER_RESPONSE

        await writer.write(
            sample_outline, "naver", sample_topic, sample_research
        )

        call_args = writer.claude.call.call_args
        assert call_args.kwargs.get("system") or call_args.args[0]
