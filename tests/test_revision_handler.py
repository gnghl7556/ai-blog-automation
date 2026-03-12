"""
수정 요청 처리기 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from approval.revision_handler import RevisionHandler, RevisionRequest
from agents.editor_agent import EditorAgent
from agents.data_models import PlatformDraft, EditResult


@pytest.fixture
def mock_editor():
    editor = MagicMock(spec=EditorAgent)
    editor.edit = AsyncMock(
        return_value=EditResult(
            content_id="naver_test_12345678",
            platform="naver",
            final_draft="수정된 본문",
            quality_score=8.5,
            quality_detail={"accuracy": 8.0, "readability": 8.5, "tone": 9.0, "grammar": 8.0, "structure": 8.5},
            edit_summary={"factcheck": "확인 완료", "readability_edits": "개선됨"},
            passed=True,
        )
    )
    return editor


@pytest.fixture
def handler(mock_editor):
    return RevisionHandler(editor=mock_editor)


@pytest.fixture
def sample_draft():
    return PlatformDraft(
        content_id="naver_test_12345678",
        topic_id="test123",
        platform="naver",
        title="테스트 제목",
        body="원본 본문 내용",
        word_count=100,
        image_placeholders=[],
    )


class TestRevisionHandler:
    @pytest.mark.asyncio
    async def test_handle_calls_editor(self, handler, mock_editor, sample_draft):
        """수정 요청 시 EditorAgent.edit가 호출되는지"""
        revision = RevisionRequest(
            content_id="naver_test_12345678",
            platform="naver",
            notes="도입부를 더 친근하게 수정해주세요",
        )

        result = await handler.handle(sample_draft, revision)

        mock_editor.edit.assert_called_once()
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_handle_prepends_revision_notes(self, handler, mock_editor, sample_draft):
        """수정 노트가 본문 앞에 추가되는지"""
        revision = RevisionRequest(
            content_id="naver_test_12345678",
            platform="naver",
            notes="비유를 더 추가해주세요",
        )

        await handler.handle(sample_draft, revision)

        call_args = mock_editor.edit.call_args[0][0]
        assert "[수정 요청]" in call_args.body
        assert "비유를 더 추가해주세요" in call_args.body
        assert "원본 본문 내용" in call_args.body

    @pytest.mark.asyncio
    async def test_handle_returns_edit_result(self, handler, sample_draft):
        """EditResult가 올바르게 반환되는지"""
        revision = RevisionRequest(
            content_id="naver_test_12345678",
            platform="naver",
            notes="수정 요청",
        )

        result = await handler.handle(sample_draft, revision)

        assert isinstance(result, EditResult)
        assert result.quality_score == 8.5
        assert result.final_draft == "수정된 본문"
