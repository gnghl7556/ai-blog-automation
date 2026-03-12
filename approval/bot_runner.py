"""
BotRunner — 텔레그램 Long Polling 루프
승인/수정/반려 콜백을 수신하고, 승인 시 자동 발행합니다.
"""

import asyncio
from typing import Optional

import httpx
import structlog

from utils.notification import TelegramNotifier
from approval.telegram_bot import ApprovalBot, ApprovalResult
from database.session import DatabaseManager
from database.repository import ContentRepository
from database.models import TopicStatus

logger = structlog.get_logger()

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class BotRunner:
    """텔레그램 Long Polling 봇 러너

    getUpdates API로 콜백 쿼리를 수신하고,
    승인 시 자동 발행까지 처리합니다.

    Args:
        db_manager: DatabaseManager 인스턴스
        notifier: TelegramNotifier (None이면 자동 생성)
        poll_timeout: Long Polling 타임아웃 (초)
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        notifier: Optional[TelegramNotifier] = None,
        poll_timeout: int = 30,
    ):
        self.db = db_manager
        self.notifier = notifier or TelegramNotifier()
        self.bot = ApprovalBot(notifier=self.notifier)
        self.repo = ContentRepository(db_manager)
        self.poll_timeout = poll_timeout
        self.logger = logger.bind(module="bot_runner")
        self._running = False
        self._offset = 0

    async def start(self) -> None:
        """Polling 루프 시작 (Ctrl+C로 종료)"""
        self._running = True
        self.logger.info("bot_runner.start", timeout=self.poll_timeout)

        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._process_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "bot_runner.poll_error", error=str(e),
                )
                await asyncio.sleep(5)

        self.logger.info("bot_runner.stopped")

    def stop(self) -> None:
        """Polling 루프 중지"""
        self._running = False

    async def _get_updates(self) -> list[dict]:
        """Telegram getUpdates API 호출 (Long Polling)"""
        url = TELEGRAM_API.format(
            token=self.notifier.bot_token, method="getUpdates",
        )
        params = {
            "offset": self._offset,
            "timeout": self.poll_timeout,
            "allowed_updates": '["callback_query"]',
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params,
                    timeout=self.poll_timeout + 10,
                )
                data = response.json()
        except httpx.TimeoutException:
            return []

        if not data.get("ok"):
            self.logger.error(
                "bot_runner.get_updates_failed",
                error=data.get("description"),
            )
            return []

        results = data.get("result", [])
        if results:
            self._offset = results[-1]["update_id"] + 1
        return results

    async def _process_update(self, update: dict) -> None:
        """단일 업데이트 처리"""
        callback_query = update.get("callback_query")
        if not callback_query:
            return

        callback_data = callback_query.get("data", "")
        callback_query_id = str(callback_query.get("id", ""))

        self.logger.info(
            "bot_runner.callback_received",
            data=callback_data,
        )

        result = await self.bot.handle_callback(
            callback_data, callback_query_id,
        )

        await self._handle_approval_result(result)

    async def _handle_approval_result(
        self, result: ApprovalResult
    ) -> None:
        """승인 결과에 따른 DB 업데이트 + 자동 발행"""
        topic_id = result.topic_id

        if result.action == "approved":
            await self._handle_approve(topic_id)
        elif result.action == "rejected":
            await self._handle_reject(topic_id)
        elif result.action == "revised":
            await self._handle_revise(topic_id)

    async def _handle_approve(self, topic_id: str) -> None:
        """승인 처리: DB 업데이트 → 자동 발행"""
        # 1. DB 상태 변경
        self.repo.update_topic_status(topic_id, TopicStatus.APPROVED)
        contents = self.repo.get_contents_by_topic(topic_id)
        for c in contents:
            self.repo.save_approval_log(c.id, "approved", "텔레그램 승인")

        self.logger.info("bot_runner.approved", topic_id=topic_id)

        # 2. 자동 발행
        await self._auto_publish(topic_id)

    async def _handle_reject(self, topic_id: str) -> None:
        """반려 처리: DB 상태만 변경"""
        self.repo.update_topic_status(topic_id, TopicStatus.REJECTED)
        contents = self.repo.get_contents_by_topic(topic_id)
        for c in contents:
            self.repo.save_approval_log(c.id, "rejected", "텔레그램 반려")

        await self.bot.send_result_notification(
            topic_id, "rejected", "반려 처리되었습니다.",
        )
        self.logger.info("bot_runner.rejected", topic_id=topic_id)

    async def _handle_revise(self, topic_id: str) -> None:
        """수정 요청 처리: DB 상태 변경 + 알림"""
        self.repo.update_topic_status(topic_id, TopicStatus.EDITING)
        contents = self.repo.get_contents_by_topic(topic_id)
        for c in contents:
            self.repo.save_approval_log(c.id, "revised", "텔레그램 수정 요청")

        await self.bot.send_result_notification(
            topic_id, "revised",
            "수정이 필요합니다. CLI에서 재생성하세요.",
        )
        self.logger.info("bot_runner.revision_requested", topic_id=topic_id)

    async def _auto_publish(self, topic_id: str) -> None:
        """승인 후 자동 발행"""
        from utils.claude_client import ClaudeClient
        from pipeline import Pipeline
        import os

        self.logger.info("bot_runner.auto_publish.start", topic_id=topic_id)

        try:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            client = ClaudeClient(api_key=api_key)
            pipe = Pipeline(client, db_manager=self.db, notifier=self.notifier)
            result = await pipe.publish(topic_id)

            if result.status == "published":
                await self.bot.send_result_notification(
                    topic_id, "approved",
                    "발행 완료!\n"
                    f"네이버: {result.naver_publish_result.published_url or '실패'}\n"
                    f"티스토리: {result.tistory_publish_result.published_url or '실패'}",
                )
            else:
                await self.bot.send_result_notification(
                    topic_id, "approved",
                    f"발행 부분 실패 (status: {result.status})",
                )

            self.logger.info(
                "bot_runner.auto_publish.complete",
                topic_id=topic_id,
                status=result.status,
            )
        except Exception as e:
            self.logger.error(
                "bot_runner.auto_publish.failed",
                topic_id=topic_id,
                error=str(e),
            )
            await self.notifier.send_message(
                f"<b>발행 실패</b>\n주제: {topic_id}\n에러: {str(e)}"
            )
