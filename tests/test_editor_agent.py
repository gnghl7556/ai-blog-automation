"""
EditorAgent 테스트
"""

import json

import pytest

from agents.editor_agent import EditorAgent
from agents.data_models import PlatformDraft, EditResult


@pytest.fixture
def editor(mock_claude_client):
    """EditorAgent 인스턴스 (mock Claude)"""
    return EditorAgent(mock_claude_client)


@pytest.fixture
def sample_naver_draft():
    return PlatformDraft(
        content_id="naver_test_001_abc12345",
        topic_id="test_001",
        platform="naver",
        title="AI 비서 Claude가 진화했거든요",
        body=(
            "얼마 전에 친구가 저한테 이러더라고요.\n\n"
            "## Claude가 뭔데?\n\n"
            "쉽게 말하면 AI 비서거든요.\n\n"
            "[이미지: Claude 소개]\n\n"
            "정리하면 이렇거든요. 첫째, 더 똑똑해졌어요."
        ),
        word_count=150,
        image_placeholders=[{"position": 5, "description": "Claude 소개"}],
    )


@pytest.fixture
def sample_tistory_draft():
    return PlatformDraft(
        content_id="tistory_test_001_def67890",
        topic_id="test_001",
        platform="tistory",
        title="Claude 4 심층 분석",
        body=(
            "Anthropic이 Claude 4를 발표했습니다.\n\n"
            "## 주요 변경사항\n\n"
            "컨텍스트 윈도우가 확대되었습니다."
        ),
        word_count=100,
    )


def make_edit_response(text: str, summary: str = "수정 완료") -> str:
    """편집 단계 응답 포맷"""
    return f"{text}\n---\n{summary}"


def make_quality_response(
    accuracy: int = 8, readability: int = 8,
    engagement: int = 8, structure: int = 8, tone: int = 8,
) -> str:
    """품질 평가 응답"""
    return json.dumps({
        "accuracy": accuracy,
        "readability": readability,
        "engagement": engagement,
        "structure": structure,
        "tone": tone,
    })


class TestEditorAgent:
    @pytest.mark.asyncio
    async def test_edit_returns_edit_result(self, editor, sample_naver_draft):
        """edit()이 EditResult를 반환하는지 확인"""
        # 4단계 편집 + 1 품질 평가 = 5번 호출
        editor.claude.call.side_effect = [
            make_edit_response("팩트체크 완료 본문", "팩트 수정 1건"),
            make_edit_response("가독성 개선 본문", "문단 분리 2건"),
            make_edit_response("톤 수정 본문", "~거든요 체 통일"),
            make_edit_response("맞춤법 수정 본문", "띄어쓰기 3건"),
            make_quality_response(),
        ]

        result = await editor.edit(sample_naver_draft)

        assert isinstance(result, EditResult)
        assert result.content_id == "naver_test_001_abc12345"
        assert result.platform == "naver"

    @pytest.mark.asyncio
    async def test_quality_score_calculation(self, editor, sample_naver_draft):
        """가중 평균 품질 점수 계산 확인"""
        editor.claude.call.side_effect = [
            make_edit_response("본문", "수정 없음"),
            make_edit_response("본문", "수정 없음"),
            make_edit_response("본문", "수정 없음"),
            make_edit_response("본문", "수정 없음"),
            make_quality_response(accuracy=10, readability=8, engagement=6, structure=8, tone=8),
        ]

        result = await editor.edit(sample_naver_draft)

        # 가중 평균: 10*0.2 + 8*0.2 + 6*0.2 + 8*0.2 + 8*0.2 = 8.0
        assert result.quality_score == 8.0

    @pytest.mark.asyncio
    async def test_quality_pass(self, editor, sample_naver_draft):
        """품질 7.5 이상이면 passed=True"""
        editor.claude.call.side_effect = [
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_quality_response(accuracy=8, readability=8, engagement=8, structure=8, tone=8),
        ]

        result = await editor.edit(sample_naver_draft)

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_quality_fail(self, editor, sample_naver_draft):
        """품질 7.5 미만이면 passed=False"""
        editor.claude.call.side_effect = [
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_quality_response(accuracy=5, readability=5, engagement=5, structure=5, tone=5),
        ]

        result = await editor.edit(sample_naver_draft)

        assert result.passed is False
        assert result.quality_score == 5.0

    @pytest.mark.asyncio
    async def test_edit_summary_populated(self, editor, sample_naver_draft):
        """edit_summary에 4단계 내역이 포함되는지 확인"""
        editor.claude.call.side_effect = [
            make_edit_response("본문", "팩트 수정 1건"),
            make_edit_response("본문", "문단 분리"),
            make_edit_response("본문", "톤 통일"),
            make_edit_response("본문", "띄어쓰기 수정"),
            make_quality_response(),
        ]

        result = await editor.edit(sample_naver_draft)

        assert "factcheck" in result.edit_summary
        assert "readability" in result.edit_summary
        assert "tone" in result.edit_summary
        assert "grammar" in result.edit_summary

    @pytest.mark.asyncio
    async def test_four_editing_stages_called(self, editor, sample_naver_draft):
        """Claude API가 5번 호출되는지 확인 (편집 4 + 평가 1)"""
        editor.claude.call.side_effect = [
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_quality_response(),
        ]

        await editor.edit(sample_naver_draft)

        assert editor.claude.call.call_count == 5

    @pytest.mark.asyncio
    async def test_tistory_edit(self, editor, sample_tistory_draft):
        """티스토리 글 편집도 정상 동작하는지 확인"""
        editor.claude.call.side_effect = [
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_edit_response("본문"),
            make_quality_response(),
        ]

        result = await editor.edit(sample_tistory_draft)

        assert result.platform == "tistory"
        assert isinstance(result, EditResult)
