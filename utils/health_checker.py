"""
헬스체크 모듈 — 핵심 의존성 상태 확인
DB 연결, Claude API, Telegram Bot 상태를 점검합니다.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


@dataclass
class CheckResult:
    """개별 헬스체크 결과"""

    name: str
    healthy: bool
    message: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthReport:
    """전체 헬스체크 보고서"""

    checks: list[CheckResult] = field(default_factory=list)
    checked_at: str = ""

    @property
    def all_healthy(self) -> bool:
        return all(c.healthy for c in self.checks)

    @property
    def summary(self) -> str:
        total = len(self.checks)
        healthy = sum(1 for c in self.checks if c.healthy)
        return f"{healthy}/{total} healthy"


class HealthChecker:
    """핵심 의존성 헬스체크

    DB 연결, Claude API 키, Telegram Bot 연결을 점검합니다.
    """

    def __init__(self):
        self.logger = logger.bind(module="health_checker")

    async def check_all(self) -> HealthReport:
        """모든 헬스체크 실행

        Returns:
            HealthReport: 전체 점검 결과
        """
        report = HealthReport(
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        report.checks.append(self._check_db())
        report.checks.append(self._check_claude_api_key())
        report.checks.append(await self._check_telegram())
        report.checks.append(self._check_directories())

        return report

    def _check_db(self) -> CheckResult:
        """DB 연결 상태 확인"""
        import time

        try:
            start = time.monotonic()
            from database.session import DatabaseManager

            db = DatabaseManager()
            with db.get_session() as session:
                session.execute(
                    __import__(
                        "sqlalchemy", fromlist=["text"]
                    ).text("SELECT 1")
                )
            elapsed = (time.monotonic() - start) * 1000

            return CheckResult(
                name="database",
                healthy=True,
                message="연결 정상",
                latency_ms=round(elapsed, 1),
            )
        except Exception as e:
            return CheckResult(
                name="database",
                healthy=False,
                message=f"연결 실패: {e}",
            )

    def _check_claude_api_key(self) -> CheckResult:
        """Claude API 키 존재 및 형식 확인"""
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key.strip():
            return CheckResult(
                name="claude_api",
                healthy=False,
                message="ANTHROPIC_API_KEY 미설정",
            )

        if not api_key.startswith("sk-ant-"):
            return CheckResult(
                name="claude_api",
                healthy=False,
                message="API 키 형식 이상 (sk-ant- 접두사 필요)",
            )

        return CheckResult(
            name="claude_api",
            healthy=True,
            message=f"키 설정됨 (***{api_key[-4:]})",
        )

    async def _check_telegram(self) -> CheckResult:
        """Telegram Bot 연결 확인 (getMe API 호출)"""
        import time

        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            return CheckResult(
                name="telegram",
                healthy=False,
                message="TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정",
            )

        try:
            import httpx

            start = time.monotonic()
            url = f"https://api.telegram.org/bot{token}/getMe"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                data = resp.json()
            elapsed = (time.monotonic() - start) * 1000

            if data.get("ok"):
                bot_name = data["result"].get("username", "unknown")
                return CheckResult(
                    name="telegram",
                    healthy=True,
                    message=f"봇 연결 정상 (@{bot_name})",
                    latency_ms=round(elapsed, 1),
                )
            else:
                return CheckResult(
                    name="telegram",
                    healthy=False,
                    message=f"API 오류: {data.get('description', 'unknown')}",
                )
        except Exception as e:
            return CheckResult(
                name="telegram",
                healthy=False,
                message=f"연결 실패: {e}",
            )

    def _check_directories(self) -> CheckResult:
        """필수 디렉토리 존재 확인"""
        from pathlib import Path

        required = ["data", "logs", "config"]
        missing = [d for d in required if not Path(d).exists()]

        if missing:
            return CheckResult(
                name="directories",
                healthy=False,
                message=f"누락: {', '.join(missing)}",
            )

        return CheckResult(
            name="directories",
            healthy=True,
            message="필수 디렉토리 모두 존재",
        )
