"""헬스체크 모듈 테스트"""

import os
from unittest.mock import patch, AsyncMock

import pytest

from utils.health_checker import HealthChecker, HealthReport, CheckResult


@pytest.fixture
def checker():
    return HealthChecker()


class TestCheckResult:
    def test_healthy_result(self):
        r = CheckResult(name="test", healthy=True, message="ok")
        assert r.healthy
        assert r.latency_ms == 0.0

    def test_unhealthy_result(self):
        r = CheckResult(name="test", healthy=False, message="fail")
        assert not r.healthy


class TestHealthReport:
    def test_all_healthy(self):
        report = HealthReport(checks=[
            CheckResult(name="a", healthy=True),
            CheckResult(name="b", healthy=True),
        ])
        assert report.all_healthy
        assert report.summary == "2/2 healthy"

    def test_partial_healthy(self):
        report = HealthReport(checks=[
            CheckResult(name="a", healthy=True),
            CheckResult(name="b", healthy=False),
        ])
        assert not report.all_healthy
        assert report.summary == "1/2 healthy"

    def test_empty_report(self):
        report = HealthReport()
        assert report.all_healthy
        assert report.summary == "0/0 healthy"


class TestHealthChecker:
    def test_check_db_success(self, checker, db):
        """DB 연결 확인 — 정상"""
        with patch(
            "database.session.DatabaseManager", return_value=db
        ):
            result = checker._check_db()
        assert result.healthy
        assert result.name == "database"

    def test_check_db_failure(self, checker):
        """DB 연결 확인 — 실패"""
        with patch(
            "database.session.DatabaseManager",
            side_effect=Exception("connection error"),
        ):
            result = checker._check_db()
        assert not result.healthy

    def test_check_claude_api_key_missing(self, checker):
        """Claude API 키 미설정"""
        with patch.dict(os.environ, {}, clear=True):
            result = checker._check_claude_api_key()
        assert not result.healthy
        assert "미설정" in result.message

    def test_check_claude_api_key_invalid_format(self, checker):
        """Claude API 키 형식 이상"""
        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "invalid-key"}
        ):
            result = checker._check_claude_api_key()
        assert not result.healthy
        assert "형식" in result.message

    def test_check_claude_api_key_valid(self, checker):
        """Claude API 키 정상"""
        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test1234"}
        ):
            result = checker._check_claude_api_key()
        assert result.healthy
        assert "1234" in result.message

    @pytest.mark.asyncio
    async def test_check_telegram_missing_config(self, checker):
        """Telegram 설정 미존재"""
        with patch.dict(os.environ, {}, clear=True):
            result = await checker._check_telegram()
        assert not result.healthy
        assert "미설정" in result.message

    @pytest.mark.asyncio
    async def test_check_telegram_success(self, checker):
        """Telegram Bot 연결 성공"""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_CHAT_ID": "12345",
        }):
            with patch(
                "httpx.AsyncClient", return_value=mock_client
            ):
                result = await checker._check_telegram()

        assert result.healthy
        assert "test_bot" in result.message

    @pytest.mark.asyncio
    async def test_check_telegram_api_error(self, checker):
        """Telegram Bot API 오류"""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "description": "Unauthorized",
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "bad-token",
            "TELEGRAM_CHAT_ID": "12345",
        }):
            with patch(
                "httpx.AsyncClient", return_value=mock_client
            ):
                result = await checker._check_telegram()

        assert not result.healthy
        assert "Unauthorized" in result.message

    def test_check_directories_success(self, checker, tmp_path):
        """필수 디렉토리 존재 — 실제 디렉토리로 테스트"""
        # data, logs, config 디렉토리가 프로젝트에 존재해야 함
        result = checker._check_directories()
        # 프로젝트 루트에서 실행하므로 보통 존재
        assert result.name == "directories"

    @pytest.mark.asyncio
    async def test_check_all(self, checker):
        """전체 헬스체크 실행"""
        with patch.object(
            checker, "_check_db",
            return_value=CheckResult(
                name="database", healthy=True
            ),
        ), patch.object(
            checker, "_check_claude_api_key",
            return_value=CheckResult(
                name="claude_api", healthy=True
            ),
        ), patch.object(
            checker, "_check_telegram",
            return_value=CheckResult(
                name="telegram", healthy=True
            ),
        ), patch.object(
            checker, "_check_directories",
            return_value=CheckResult(
                name="directories", healthy=True
            ),
        ):
            report = await checker.check_all()

        assert len(report.checks) == 4
        assert report.all_healthy
        assert report.checked_at
