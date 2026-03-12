"""
Pipeline 오케스트레이터 — 전체 글 생성 파이프라인 조율
리서치 → 관점분화 → [네이버작성 | 티스토리작성] (병렬)
→ [편집] (병렬) → [SEO] (병렬) → 포맷 변환 → 품질검사
→ DB 저장 → 텔레그램 승인 요청 → 발행
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

import structlog

from agents.research_agent import ResearchAgent
from agents.content_splitter import ContentSplitter
from agents.writing_agent import WritingAgent
from agents.editor_agent import EditorAgent
from agents.seo_agent import SEOAgent
from agents.quality_checker import QualityChecker, QualityReport
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    SplitOutlines,
    PlatformDraft,
    EditResult,
    SEOResult,
    PublishResult,
)
from utils.claude_client import ClaudeClient
from utils.text_utils import markdown_to_html, ensure_markdown
from pipeline_publish import PublishMixin

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
    naver_seo: Optional[SEOResult] = None
    tistory_seo: Optional[SEOResult] = None
    naver_html: str = ""
    tistory_markdown: str = ""
    quality_report: Optional[QualityReport] = None
    status: str = "pending"
    # Phase 3A 추가 필드
    naver_content_id: Optional[str] = None
    tistory_content_id: Optional[str] = None
    approval_message_id: Optional[int] = None
    naver_publish_result: Optional[PublishResult] = None
    tistory_publish_result: Optional[PublishResult] = None


class Pipeline(PublishMixin):
    """글 생성 파이프라인 오케스트레이터

    전체 파이프라인을 단계별로 실행하고
    네이버/티스토리 작성·편집·SEO를 병렬로 처리합니다.

    Args:
        claude_client: Claude API 클라이언트
        db_manager: DatabaseManager (None이면 DB 저장 스킵)
        notifier: TelegramNotifier (None이면 승인 요청 스킵)
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        db_manager=None,
        notifier=None,
    ):
        self.claude = claude_client
        self.researcher = ResearchAgent(claude_client)
        self.splitter = ContentSplitter(claude_client)
        self.writer = WritingAgent(claude_client)
        self.editor = EditorAgent(claude_client)
        self.seo = SEOAgent(claude_client)
        self.checker = QualityChecker()
        self.db = db_manager
        self.notifier = notifier
        self.logger = logger.bind(module="pipeline")

    async def run(
        self,
        topic: str,
        content_type: str = "news_briefing",
        category: str = "ai_products",
        keywords: Optional[list[str]] = None,
        source: str = "manual_input",
        source_url: str = "",
    ) -> PipelineResult:
        """전체 파이프라인 실행 (글 생성 → DB 저장 → 승인 요청)

        Args:
            topic: 글 주제
            content_type: 글 유형
            category: 카테고리
            keywords: 키워드 목록
            source: 출처 (예: rss, manual_input)
            source_url: 원본 URL

        Returns:
            PipelineResult: 파이프라인 결과
        """
        kw = keywords or []
        topic_id = uuid.uuid4().hex[:12]
        topic_pkg = TopicPackage(
            topic_id=topic_id,
            title=topic,
            keywords=kw,
            category=category,
            content_type=content_type,
            source=source,
            source_url=source_url,
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
            self.writer.write(outlines.naver, "naver", topic_pkg, research),
            self.writer.write(outlines.tistory, "tistory", topic_pkg, research),
        )

        # 4단계: 편집 (네이버 + 티스토리 병렬)
        self.logger.info("pipeline.stage", stage="edit")
        naver_edited, tistory_edited = await asyncio.gather(
            self.editor.edit(naver_draft),
            self.editor.edit(tistory_draft),
        )

        # 5단계: SEO 최적화 (네이버 + 티스토리 병렬)
        self.logger.info("pipeline.stage", stage="seo")
        naver_seo, tistory_seo = await asyncio.gather(
            self.seo.optimize(naver_edited, kw),
            self.seo.optimize(tistory_edited, kw),
        )

        # 6단계: 포맷 변환
        self.logger.info("pipeline.stage", stage="format")
        naver_html = markdown_to_html(naver_seo.optimized_body)
        tistory_md = ensure_markdown(tistory_seo.optimized_body)

        # 7단계: 품질 검사
        self.logger.info("pipeline.stage", stage="quality_check")
        quality_report = self.checker.check(naver_edited, tistory_edited)

        quality_status = (
            "success" if quality_report.all_passed else "quality_failed"
        )

        result = PipelineResult(
            topic=topic_pkg,
            research=research,
            outlines=outlines,
            naver_draft=naver_draft,
            tistory_draft=tistory_draft,
            naver_edited=naver_edited,
            tistory_edited=tistory_edited,
            naver_seo=naver_seo,
            tistory_seo=tistory_seo,
            naver_html=naver_html,
            tistory_markdown=tistory_md,
            quality_report=quality_report,
            status=quality_status,
        )

        # 8단계: DB 저장 (db_manager가 있을 때만)
        if self.db:
            self.logger.info("pipeline.stage", stage="db_save")
            result = self._save_to_db(result, naver_html, tistory_md)

        # 9단계: 텔레그램 승인 요청 (notifier가 있을 때만)
        if self.db and self.notifier:
            self.logger.info("pipeline.stage", stage="approval_request")
            result = await self._request_approval(result)

        self.logger.info(
            "pipeline.complete",
            topic_id=topic_id,
            status=result.status,
            naver_quality=naver_edited.quality_score,
            tistory_quality=tistory_edited.quality_score,
            naver_seo=naver_seo.seo_score,
            tistory_seo=tistory_seo.seo_score,
            similarity=quality_report.similarity,
        )

        return result

    def _save_to_db(
        self,
        result: PipelineResult,
        naver_html: str,
        tistory_md: str,
    ) -> PipelineResult:
        """파이프라인 결과를 DB에 저장"""
        from database.repository import ContentRepository

        repo = ContentRepository(self.db)

        repo.save_topic(result.topic)

        naver_content_id = repo.save_content(
            topic_id=result.topic.topic_id,
            platform="naver",
            edit_result=result.naver_edited,
            seo_result=result.naver_seo,
            body_final=naver_html,
        )
        tistory_content_id = repo.save_content(
            topic_id=result.topic.topic_id,
            platform="tistory",
            edit_result=result.tistory_edited,
            seo_result=result.tistory_seo,
            body_final=tistory_md,
        )

        from database.models import TopicStatus
        repo.update_topic_status(
            result.topic.topic_id, TopicStatus.REVIEW
        )

        result.naver_content_id = naver_content_id
        result.tistory_content_id = tistory_content_id
        result.status = "pending_approval"

        self.logger.info(
            "pipeline.db_saved",
            topic_id=result.topic.topic_id,
            naver_content_id=naver_content_id,
            tistory_content_id=tistory_content_id,
        )
        return result

    async def _request_approval(
        self, result: PipelineResult
    ) -> PipelineResult:
        """텔레그램 승인 요청 전송"""
        from approval.telegram_bot import ApprovalBot

        bot = ApprovalBot(notifier=self.notifier)
        try:
            message_id = await bot.request_approval(result)
            result.approval_message_id = message_id
        except Exception as e:
            self.logger.error(
                "pipeline.approval_request_failed",
                error=str(e),
            )
        return result

    # publish() 및 _notify_publish_result()는
    # PublishMixin (pipeline_publish.py)에서 제공됩니다.
