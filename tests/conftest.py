"""
테스트 공통 설정 — Fixtures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from utils.claude_client import ClaudeClient


@pytest.fixture
def mock_claude_client() -> ClaudeClient:
    """Claude API 클라이언트 목 객체

    실제 API 호출 없이 에이전트를 테스트할 수 있도록
    call() 메서드를 AsyncMock으로 대체합니다.
    """
    client = MagicMock(spec=ClaudeClient)
    client.call = AsyncMock(return_value="mock response")
    client.cost_tracker = MagicMock()
    return client
