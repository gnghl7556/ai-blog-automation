"""
SchedulerRunner — 스케줄러 + 텔레그램 봇 통합 러너
하나의 asyncio 이벤트 루프에서 스케줄러와 봇을 병렬 실행합니다.
"""

import asyncio
import os

import structlog

from scheduler.scheduler import BlogScheduler

logger = structlog.get_logger()


class SchedulerRunner:
    """스케줄러 + 텔레그램 봇 통합 러너

    하나의 asyncio 이벤트 루프에서:
    1. APScheduler로 수집/큐레이션/생성 자동 실행
    2. 텔레그램 Long Polling으로 승인 콜백 수신 (설정 있을 때)
    """

    def __init__(
        self, config_path: str = "config/schedule.yaml"
    ):
        self.logger = logger.bind(module="scheduler_runner")
        self.scheduler = BlogScheduler(config_path=config_path)
        self.bot_runner = None
        self._stop_event = asyncio.Event()

    def _has_telegram_config(self) -> bool:
        """텔레그램 봇 설정 존재 여부 확인

        Returns:
            TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID 모두 있으면 True
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        return bool(token and chat_id)

    def _create_bot_runner(self):
        """BotRunner 인스턴스 생성

        Returns:
            BotRunner
        """
        from database.session import DatabaseManager
        from approval.bot_runner import BotRunner
        from utils.notification import TelegramNotifier

        db = DatabaseManager()
        db.create_tables()
        notifier = TelegramNotifier()
        return BotRunner(db_manager=db, notifier=notifier)

    async def start(self) -> None:
        """통합 러너 시작

        1. 스케줄러 시작
        2. 텔레그램 봇 시작 (설정 있으면)
        3. asyncio.gather로 병렬 실행
        """
        self.logger.info("scheduler_runner.starting")

        # DB 테이블 확인
        from database.session import DatabaseManager
        db = DatabaseManager()
        db.create_tables()

        # 스케줄러 시작
        self.scheduler.start()

        # 다음 실행 시간 로깅
        for info in self.scheduler.get_next_runs():
            self.logger.info(
                "scheduler_runner.next_run",
                job=info["job"],
                next_run=str(info["next_run"]),
            )

        # 병렬 실행
        tasks = []

        if self._has_telegram_config():
            self.bot_runner = self._create_bot_runner()
            self.logger.info(
                "scheduler_runner.bot_enabled"
            )
            tasks.append(self.bot_runner.start())
        else:
            self.logger.info(
                "scheduler_runner.bot_disabled",
                reason="텔레그램 설정 없음",
            )
            tasks.append(self._stop_event.wait())

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """통합 러너 정지"""
        self.logger.info("scheduler_runner.stopping")

        if self.bot_runner:
            self.bot_runner.stop()

        self.scheduler.stop()
        self._stop_event.set()

        self.logger.info("scheduler_runner.stopped")
