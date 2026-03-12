"""
Pipeline 오케스트레이터 — 전체 글 생성 파이프라인 조율
리서치 → 관점분화 → [네이버작성 | 티스토리작성] (병렬)
→ [네이버편집 | 티스토리편집] (병렬) → 품질검사 → 결과 반환
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

import structlog

from agents.research_agent import ResearchAgent
from agents.content_splitter import ContentSplitter
from agents.writing_agent import WritingAgent
from agents.editor_agent import EditorAgent
from agents.quality_checker import QualityChecker, QualityReport
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    SplitOutlines,
    PlatformDraft,
    EditResult,
)
from utils.claude_client import ClaudeClient

logger = structlog.get_logger()


@dataclass
class PipelineResult:
    """파이프라인 최종 결과"""

    topic: TopicPackage
    research: ResearchNote
    outlines: SplitOutlines
    naver_draft: PlatformDraft
    tistory_draft: PlatformDraft
    naver_edited: EditResult
    tistory_edited: EditResult
    quality_report: QualityReport
    status: str  # "success" | "quality_failed"


class Pipeline:
    """글 생성 파이프라인 오케스트레이터

    전체 파이프라인을 단계별로 실행하고
    네이버/티스토리 작성·편집을 병렬로 처리합니다.
    """

    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.researcher = ResearchAgent(claude_client)
        self.splitter = ContentSplitter(claude_client)
        self.writer = WritingAgent(claude_client)
        self.editor = EditorAgent(claude_client)
        self.checker = QualityChecker()
        self.logger = logger.bind(module="pipeline")

    async def run(
        self,
        topic: str,
        content_type: str = "news_briefing",
        category: str = "ai_products",
        keywords: Optional[list[str]] = None,
    ) -> PipelineResult:
        """전체 파이프라인 실행

        Args:
            topic: 글 주제
            content_type: 글 유형
            category: 카테고리
            keywords: 키워드 목록

        Returns:
            PipelineResult: 파이프라인 결과
        """
        topic_id = uuid.uuid4().hex[:12]
        topic_pkg = TopicPackage(
            topic_id=topic_id,
            title=topic,
            keywords=keywords or [],
            category=category,
            content_type=content_type,
            source="manual_input",
            curator_score=0.0,
        )

        self.logger.info("pipeline.start", topic_id=topic_id, title=topic)

        # 1단계: 리서치
        self.logger.info("pipeline.stage", stage="research")
        research = await self.researcher.research(topic_pkg)

        # 2단계: 관점 분화
        self.logger.info("pipeline.stage", stage="split")
        outlines = await self.splitter.split(topic_pkg, research)

        # 3단계: 작성 (네이버 + 티스토리 병렬)
        self.logger.info("pipeline.stage", stage="write")
        naver_draft, tistory_draft = await asyncio.gather(
            self.writer.write(
                outlines.naver, "naver", topic_pkg, research
            ),
            self.writer.write(
                outlines.tistory, "tistory", topic_pkg, research
            ),
        )

        # 4단계: 편집 (네이버 + 티스토리 병렬)
        self.logger.info("pipeline.stage", stage="edit")
        naver_edited, tistory_edited = await asyncio.gather(
            self.editor.edit(naver_draft),
            self.editor.edit(tistory_draft),
        )

        # 5단계: 품질 검사
        self.logger.info("pipeline.stage", stage="quality_check")
        quality_report = self.checker.check(naver_edited, tistory_edited)

        status = "success" if quality_report.all_passed else "quality_failed"

        self.logger.info(
            "pipeline.complete",
            topic_id=topic_id,
            status=status,
            naver_score=naver_edited.quality_score,
            tistory_score=tistory_edited.quality_score,
            similarity=quality_report.similarity,
        )

        return PipelineResult(
            topic=topic_pkg,
            research=research,
            outlines=outlines,
            naver_draft=naver_draft,
            tistory_draft=tistory_draft,
            naver_edited=naver_edited,
            tistory_edited=tistory_edited,
            quality_report=quality_report,
            status=status,
        )
