"""
BaseAgent — 모든 에이전트의 기본 클래스
Claude API 호출, 에러 처리, 프롬프트 로딩을 제공합니다.
"""

import yaml
from pathlib import Path
from typing import Optional

import structlog

from utils.claude_client import ClaudeClient, ClaudeAPIError

logger = structlog.get_logger()


class AgentError(Exception):
    """에이전트 에러"""

    def __init__(
        self, agent_name: str, stage: str, message: str, recoverable: bool = True
    ):
        self.agent_name = agent_name
        self.stage = stage
        self.recoverable = recoverable
        super().__init__(f"[{agent_name}:{stage}] {message}")


class BaseAgent:
    """모든 에이전트의 기본 클래스"""

    def __init__(self, name: str, claude_client: ClaudeClient):
        self.name = name
        self.claude = claude_client
        self.logger = logger.bind(agent=name)
        self._prompt_cache: dict[str, str] = {}

    async def claude_call(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Claude API 호출 (BaseAgent 래퍼)
        비용 추적 시 에이전트 이름이 자동으로 기록됩니다.
        """
        try:
            return await self.claude.call(
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=temperature,
                caller=self.name,
            )
        except ClaudeAPIError as e:
            raise AgentError(
                self.name, "claude_call", str(e), recoverable=e.recoverable
            )

    def load_prompt(self, prompt_path: str) -> str:
        """
        YAML 프롬프트 파일에서 system_prompt 로드

        Args:
            prompt_path: config/prompts/ 기준 상대 경로
                         예: "writing/news_briefing.yaml"
        """
        if prompt_path in self._prompt_cache:
            return self._prompt_cache[prompt_path]

        full_path = Path("config/prompts") / prompt_path
        if not full_path.exists():
            raise FileNotFoundError(f"프롬프트 파일 없음: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        prompt = data.get("system_prompt", "")
        self._prompt_cache[prompt_path] = prompt
        self.logger.debug("prompt.loaded", path=prompt_path)
        return prompt

    def load_persona(self, platform: str) -> str:
        """
        플랫폼별 페르소나 프롬프트 로드

        Args:
            platform: "naver" 또는 "tistory"
        """
        path = Path(f"config/prompts/writing/persona_{platform}.yaml")
        if not path.exists():
            raise FileNotFoundError(f"페르소나 파일 없음: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return data.get("system_prompt", "")

    def load_config(self, config_name: str) -> dict:
        """
        config/ 디렉토리에서 YAML 설정 파일 로드

        Args:
            config_name: 파일명 (확장자 포함)
                         예: "categories.yaml", "settings.yaml"
        """
        path = Path("config") / config_name
        if not path.exists():
            raise FileNotFoundError(f"설정 파일 없음: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def run_with_error_handling(self, func, *args, **kwargs):
        """에이전트 작업 실행 + 에러 처리 래퍼"""
        try:
            result = await func(*args, **kwargs)
            self.logger.info("agent.task.success")
            return result

        except AgentError as e:
            self.logger.error("agent.task.error", error=str(e), recoverable=e.recoverable)
            return {
                "status": "retry" if e.recoverable else "failed",
                "error": str(e),
                "agent": self.name,
                "stage": e.stage,
            }

        except Exception as e:
            self.logger.critical("agent.task.unexpected", error=str(e), exc_info=True)
            return {
                "status": "critical",
                "error": str(e),
                "agent": self.name,
            }
