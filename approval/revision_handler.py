"""
RevisionHandler — 수정 요청 처리
텔레그램에서 수정 요청이 들어오면 EditorAgent를 재실행합니다.
"""

from dataclasses import dataclass
from typing import Optional

import structlog

from agents.editor_agent import EditorAgent
from agents.data_models import PlatformDraft, EditResult

logger = structlog.get_logger()


@dataclass
class RevisionRequest:
    """수정 요청 데이터"""

    content_id: str
    platform: str
    notes: str  # 수정 요청 사항


class RevisionHandler:
    """수정 요청 처리기

    승인 게이트에서 수정 요청이 들어오면
    EditorAgent를 통해 글을 재편집합니다.
    """

    def __init__(self, editor: EditorAgent):
        self.editor = editor
        self.logger = logger.bind(module="revision_handler")

    async def handle(
        self, draft: PlatformDraft, revision: RevisionRequest
    ) -> EditResult:
        """수정 요청 처리

        Args:
            draft: 원본 초안
            revision: 수정 요청 내역

        Returns:
            EditResult: 재편집 결과
        """
        self.logger.info(
            "revision.start",
            content_id=revision.content_id,
            platform=revision.platform,
            notes=revision.notes[:100],
        )

        # 수정 요청 사항을 본문 앞에 주석으로 추가하여 재편집
        revised_body = (
            f"[수정 요청] {revision.notes}\n\n"
            f"---원본---\n{draft.body}"
        )
        revised_draft = PlatformDraft(
            content_id=draft.content_id,
            topic_id=draft.topic_id,
            platform=draft.platform,
            title=draft.title,
            body=revised_body,
            word_count=draft.word_count,
            image_placeholders=draft.image_placeholders,
        )

        result = await self.editor.edit(revised_draft)

        self.logger.info(
            "revision.complete",
            content_id=revision.content_id,
            quality_score=result.quality_score,
            passed=result.passed,
        )
        return result
