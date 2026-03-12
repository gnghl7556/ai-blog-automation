"""
ApprovalBot — 텔레그램 승인 게이트
글 미리보기를 보내고 승인/수정/반려를 인라인 키보드로 처리합니다.
"""

import asyncio
import json
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass

import structlog

from utils.notification import TelegramNotifier
from approval.preview_generator import PreviewGenerator
from approval.revision_handler import RevisionRequest
from pipeline import PipelineResult

logger = structlog.get_logger()

# 인라인 키보드 콜백 데이터 접두사
CB_APPROVE = "approve"
CB_REVISE = "revise"
CB_REJECT = "reject"


@dataclass
class ApprovalResult:
    """승인 게이트 결과"""

    action: str  # "approved" | "revised" | "rejected"
    topic_id: str
    revision_notes: Optional[str] = None
    rejection_reason: Optional[str] = None


class ApprovalBot:
    """텔레그램 승인 게이트

    파이프라인 결과를 미리보기로 보내고,
    사용자가 승인/수정/반려를 선택할 때까지 대기합니다.
    """

    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier or TelegramNotifier()
        self.preview_gen = PreviewGenerator()
        self.logger = logger.bind(module="approval_bot")
        self._pending: dict[str, PipelineResult] = {}

    async def request_approval(
        self, result: PipelineResult
    ) -> int:
        """승인 요청 메시지 전송

        Args:
            result: 파이프라인 결과

        Returns:
            전송된 메시지 ID
        """
        topic_id = result.topic.topic_id
        self._pending[topic_id] = result

        preview_text = self.preview_gen.generate(result)
        keyboard = self._build_keyboard(topic_id)

        response = await self.notifier.send_message(
            text=preview_text,
            reply_markup=keyboard,
        )

        message_id = response.get("result", {}).get("message_id", 0)
        self.logger.info(
            "approval.requested",
            topic_id=topic_id,
            message_id=message_id,
        )
        return message_id

    async def handle_callback(
        self, callback_data: str, callback_query_id: str
    ) -> ApprovalResult:
        """인라인 키보드 콜백 처리

        Args:
            callback_data: 콜백 데이터 (예: "approve:abc123")
            callback_query_id: 텔레그램 콜백 쿼리 ID

        Returns:
            ApprovalResult: 승인 결과
        """
        parts = callback_data.split(":", 1)
        action = parts[0]
        topic_id = parts[1] if len(parts) > 1 else ""

        await self.notifier.answer_callback(
            callback_query_id, f"처리 중: {action}"
        )

        if action == CB_APPROVE:
            self.logger.info("approval.approved", topic_id=topic_id)
            return ApprovalResult(action="approved", topic_id=topic_id)

        elif action == CB_REJECT:
            self.logger.info("approval.rejected", topic_id=topic_id)
            return ApprovalResult(
                action="rejected",
                topic_id=topic_id,
                rejection_reason="사용자 반려",
            )

        elif action == CB_REVISE:
            self.logger.info("approval.revision_requested", topic_id=topic_id)
            return ApprovalResult(
                action="revised",
                topic_id=topic_id,
                revision_notes="수정 요청됨",
            )

        return ApprovalResult(action="rejected", topic_id=topic_id)

    async def send_result_notification(
        self, topic_id: str, action: str, details: str = ""
    ) -> None:
        """승인 결과 알림 전송"""
        emoji = {"approved": "✅", "revised": "🔄", "rejected": "❌"}.get(
            action, "❓"
        )
        await self.notifier.send_message(
            f"{emoji} <b>{action.upper()}</b>\n"
            f"주제 ID: {topic_id}\n{details}"
        )

    def _build_keyboard(self, topic_id: str) -> dict:
        """인라인 키보드 생성"""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ 승인",
                        "callback_data": f"{CB_APPROVE}:{topic_id}",
                    },
                    {
                        "text": "🔄 수정",
                        "callback_data": f"{CB_REVISE}:{topic_id}",
                    },
                    {
                        "text": "❌ 반려",
                        "callback_data": f"{CB_REJECT}:{topic_id}",
                    },
                ]
            ]
        }
