"""
Claude API 래퍼 — 재시도, 비용 추적, 로깅 내장
모든 에이전트는 이 래퍼를 통해 Claude API를 호출합니다.
"""

import asyncio
import time
from typing import Optional

import structlog
from anthropic import AsyncAnthropic, APIError, RateLimitError

from utils.cost_tracker import CostTracker

logger = structlog.get_logger()


class ClaudeClient:
    """Claude API 호출 래퍼 (재시도, 비용 추적, 로깅)"""

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        retry_delays: list[int] = [5, 15, 60],
    ):
        self.client = AsyncAnthropic(api_key=api_key)
        self.default_model = default_model
        self.max_retries = max_retries
        self.retry_delays = retry_delays
        self.cost_tracker = CostTracker()

    async def call(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        caller: str = "unknown",
    ) -> str:
        """
        Claude API 호출 (자동 재시도 + 비용 추적)

        Args:
            system: 시스템 프롬프트
            user: 사용자 메시지
            model: 모델명 (기본: claude-sonnet-4-20250514)
            max_tokens: 최대 토큰 수
            temperature: 생성 온도
            caller: 호출한 에이전트 이름 (로깅용)

        Returns:
            Claude 응답 텍스트

        Raises:
            ClaudeAPIError: 모든 재시도 실패 시
        """
        model = model or self.default_model

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()

                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )

                elapsed = time.time() - start_time

                # 비용 추적
                self.cost_tracker.log(
                    caller=caller,
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    elapsed_seconds=elapsed,
                )

                logger.info(
                    "claude_api.success",
                    caller=caller,
                    attempt=attempt + 1,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    elapsed=round(elapsed, 1),
                )

                return response.content[0].text

            except RateLimitError:
                delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                logger.warning(
                    "claude_api.rate_limit",
                    caller=caller,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_in=delay,
                )
                await asyncio.sleep(delay)

            except APIError as e:
                if e.status_code and e.status_code >= 500:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(
                        "claude_api.server_error",
                        caller=caller,
                        status_code=e.status_code,
                        attempt=attempt + 1,
                        retry_in=delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "claude_api.client_error",
                        caller=caller,
                        status_code=e.status_code,
                        message=str(e),
                    )
                    raise ClaudeAPIError(
                        f"Claude API 클라이언트 에러 {e.status_code}: {e}",
                        recoverable=False,
                    )

            except asyncio.TimeoutError:
                logger.warning(
                    "claude_api.timeout",
                    caller=caller,
                    attempt=attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    raise ClaudeAPIError(
                        "API 호출 타임아웃 (3회 연속)", recoverable=True
                    )

        raise ClaudeAPIError(
            f"{self.max_retries}회 재시도 모두 실패", recoverable=False
        )

    def get_cost_summary(self) -> dict:
        """비용 요약 조회"""
        return self.cost_tracker.get_summary()


class ClaudeAPIError(Exception):
    """Claude API 에러"""

    def __init__(self, message: str, recoverable: bool = True):
        self.recoverable = recoverable
        super().__init__(message)
