"""
텔레그램 알림 모듈 테스트
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from utils.notification import TelegramNotifier, send_error_alert


@pytest.fixture
def notifier():
    return TelegramNotifier(bot_token="test_token", chat_id="12345")


class TestTelegramNotifier:
    @pytest.mark.asyncio
    async def test_send_message_builds_payload(self, notifier):
        """send_message가 올바른 payload를 구성하는지"""
        with patch("utils.notification.httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await notifier.send_message("테스트 메시지")

            assert result["ok"] is True
            mock_client.return_value.post.assert_called_once()
            call_args = mock_client.return_value.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["text"] == "테스트 메시지"
            assert payload["chat_id"] == "12345"

    @pytest.mark.asyncio
    async def test_send_message_with_reply_markup(self, notifier):
        """인라인 키보드가 포함되는지"""
        keyboard = {"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]}

        with patch("utils.notification.httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "result": {}}
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            await notifier.send_message("테스트", reply_markup=keyboard)

            call_args = mock_client.return_value.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "reply_markup" in payload

    def test_url_format(self, notifier):
        """API URL이 올바르게 구성되는지"""
        url = notifier._url("sendMessage")
        assert "test_token" in url
        assert "sendMessage" in url

    @pytest.mark.asyncio
    async def test_request_error_handling(self, notifier):
        """API 요청 실패 시 에러 처리"""
        with patch("utils.notification.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(side_effect=Exception("네트워크 에러"))

            result = await notifier.send_message("테스트")

            assert result["ok"] is False
            assert "네트워크 에러" in result["error"]
