"""
텔레그램 승인 게이트 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from approval.telegram_bot import ApprovalBot, ApprovalResult, CB_APPROVE, CB_REVISE, CB_REJECT
from utils.notification import TelegramNotifier


@pytest.fixture
def mock_notifier():
    notifier = MagicMock(spec=TelegramNotifier)
    notifier.send_message = AsyncMock(
        return_value={"ok": True, "result": {"message_id": 42}}
    )
    notifier.answer_callback = AsyncMock(return_value={"ok": True})
    return notifier


@pytest.fixture
def bot(mock_notifier):
    return ApprovalBot(notifier=mock_notifier)


@pytest.fixture
def mock_pipeline_result():
    """PipelineResult 목 객체"""
    result = MagicMock()
    result.topic.topic_id = "test123"
    result.topic.title = "AI 테스트 주제"
    result.topic.category = "ai_products"
    result.topic.content_type = "news_briefing"
    result.naver_edited.final_draft = "네이버 본문 미리보기"
    result.naver_edited.quality_score = 8.0
    result.tistory_edited.final_draft = "티스토리 본문 미리보기"
    result.tistory_edited.quality_score = 8.5
    result.naver_seo.title_final = "네이버 SEO 제목"
    result.naver_seo.seo_score = 7.8
    result.tistory_seo.title_final = "티스토리 SEO 제목"
    result.tistory_seo.seo_score = 8.2
    result.quality_report.similarity = 0.35
    result.quality_report.issues = []
    return result


class TestApprovalBot:
    @pytest.mark.asyncio
    async def test_request_approval_sends_message(self, bot, mock_notifier, mock_pipeline_result):
        """승인 요청 시 메시지가 전송되는지"""
        msg_id = await bot.request_approval(mock_pipeline_result)

        assert msg_id == 42
        mock_notifier.send_message.assert_called_once()
        call_kwargs = mock_notifier.send_message.call_args.kwargs
        assert "reply_markup" in call_kwargs

    @pytest.mark.asyncio
    async def test_request_approval_stores_pending(self, bot, mock_pipeline_result):
        """승인 요청 후 pending에 저장되는지"""
        await bot.request_approval(mock_pipeline_result)
        assert "test123" in bot._pending

    @pytest.mark.asyncio
    async def test_handle_approve_callback(self, bot, mock_notifier):
        """승인 콜백 처리"""
        result = await bot.handle_callback("approve:topic1", "qid1")

        assert result.action == "approved"
        assert result.topic_id == "topic1"
        mock_notifier.answer_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_reject_callback(self, bot, mock_notifier):
        """반려 콜백 처리"""
        result = await bot.handle_callback("reject:topic2", "qid2")

        assert result.action == "rejected"
        assert result.topic_id == "topic2"
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_handle_revise_callback(self, bot, mock_notifier):
        """수정 콜백 처리"""
        result = await bot.handle_callback("revise:topic3", "qid3")

        assert result.action == "revised"
        assert result.topic_id == "topic3"
        assert result.revision_notes is not None

    @pytest.mark.asyncio
    async def test_handle_unknown_callback(self, bot, mock_notifier):
        """알 수 없는 콜백 처리"""
        result = await bot.handle_callback("unknown:topic4", "qid4")

        assert result.action == "rejected"

    def test_build_keyboard(self, bot):
        """인라인 키보드 생성"""
        keyboard = bot._build_keyboard("abc123")

        buttons = keyboard["inline_keyboard"][0]
        assert len(buttons) == 3
        assert "approve:abc123" in buttons[0]["callback_data"]
        assert "revise:abc123" in buttons[1]["callback_data"]
        assert "reject:abc123" in buttons[2]["callback_data"]

    @pytest.mark.asyncio
    async def test_send_result_notification(self, bot, mock_notifier):
        """결과 알림 전송"""
        await bot.send_result_notification("topic1", "approved", "성공!")

        mock_notifier.send_message.assert_called_once()
        msg = mock_notifier.send_message.call_args[0][0]
        assert "APPROVED" in msg
