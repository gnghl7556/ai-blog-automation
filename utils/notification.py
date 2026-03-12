"""
텔레그램 알림 모듈
메시지, 이미지, 인라인 키보드 전송을 지원합니다.
"""

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """텔레그램 Bot API 래퍼

    메시지 전송, 이미지 전송, 인라인 키보드를 지원합니다.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.logger = logger.bind(module="telegram")

    def _url(self, method: str) -> str:
        return TELEGRAM_API.format(token=self.bot_token, method=method)

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        """텍스트 메시지 전송

        Args:
            text: 메시지 내용 (HTML 지원)
            chat_id: 채팅 ID (미지정 시 기본값 사용)
            parse_mode: 파싱 모드 (HTML / Markdown)
            reply_markup: 인라인 키보드 등 마크업

        Returns:
            Telegram API 응답
        """
        payload: dict = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._request("sendMessage", payload)

    async def send_photo(
        self,
        photo_path: str,
        caption: str = "",
        chat_id: Optional[str] = None,
    ) -> dict:
        """이미지 전송

        Args:
            photo_path: 이미지 파일 경로
            caption: 이미지 캡션
            chat_id: 채팅 ID

        Returns:
            Telegram API 응답
        """
        target_chat = chat_id or self.chat_id
        async with httpx.AsyncClient() as client:
            with open(photo_path, "rb") as f:
                response = await client.post(
                    self._url("sendPhoto"),
                    data={"chat_id": target_chat, "caption": caption},
                    files={"photo": f},
                )
        return response.json()

    async def answer_callback(
        self, callback_query_id: str, text: str = ""
    ) -> dict:
        """콜백 쿼리 응답 (인라인 키보드 클릭 시)

        Args:
            callback_query_id: 콜백 쿼리 ID
            text: 알림 텍스트
        """
        return await self._request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text},
        )

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> dict:
        """기존 메시지 수정

        Args:
            chat_id: 채팅 ID
            message_id: 수정할 메시지 ID
            text: 새 메시지 내용
            parse_mode: 파싱 모드
        """
        return await self._request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode,
            },
        )

    async def _request(self, method: str, payload: dict) -> dict:
        """Telegram API 요청"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._url(method), json=payload, timeout=30.0
                )
                data = response.json()

            if not data.get("ok"):
                self.logger.error(
                    "telegram.api_error",
                    method=method,
                    error=data.get("description"),
                )
            return data

        except Exception as e:
            self.logger.error("telegram.request_failed", method=method, error=str(e))
            return {"ok": False, "error": str(e)}


async def send_error_alert(error_msg: str, agent_name: str = "") -> None:
    """에러 발생 시 텔레그램 알림 (편의 함수)

    Args:
        error_msg: 에러 메시지
        agent_name: 에러가 발생한 에이전트 이름
    """
    notifier = TelegramNotifier()
    prefix = f"[{agent_name}] " if agent_name else ""
    await notifier.send_message(f"🚨 <b>에러 발생</b>\n{prefix}{error_msg}")
