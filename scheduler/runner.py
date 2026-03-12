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

    async def _run_startup_healthcheck(self) -> bool:
        """시작 시 헬스체크 실행

        Returns:
            True면 모든 항목 정상, False면 실패 항목 존재
        """
        from utils.health_checker import HealthChecker

        checker = HealthChecker()
        report = await checker.check_all()

        for check in report.checks:
            if check.healthy:
                self.logger.info(
                    "healthcheck.passed",
                    name=check.name,
                    message=check.message,
                )
            else:
                self.logger.error(
                    "healthcheck.failed",
                    name=check.name,
                    message=check.message,
                )

        if not report.all_healthy:
            # 텔레그램 알림 (설정 있으면)
            if self._has_telegram_config():
                from utils.notification import TelegramNotifier
                notifier = TelegramNotifier()
                failed = [
                    c for c in report.checks if not c.healthy
                ]
                failed_names = ", ".join(
                    f"{c.name}: {c.message}" for c in failed
                )
                await notifier.send_message(
                    f"🚨 <b>헬스체크 실패</b>\n{failed_names}"
                )

        return report.all_healthy

    async def start(self) -> None:
        """통합 러너 시작

        1. 로그 설정
        2. 시작 시 헬스체크
        3. 스케줄러 시작
        4. 텔레그램 봇 시작 (설정 있으면)
        5. asyncio.gather로 병렬 실행
        """
        # 로그 설정
        from utils.log_config import setup_logging_from_config
        setup_logging_from_config()

        self.logger.info("scheduler_runner.starting")

        # 시작 시 헬스체크
        healthy = await self._run_startup_healthcheck()
        if not healthy:
            self.logger.error(
                "scheduler_runner.healthcheck_failed",
                action="프로세스를 종료합니다",
            )
            raise SystemExit(
                "헬스체크 실패 — 의존성을 확인하세요"
            )

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
