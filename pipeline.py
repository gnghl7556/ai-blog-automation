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


class Pipeline:
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
    ) -> PipelineResult:
        """전체 파이프라인 실행 (글 생성 → DB 저장 → 승인 요청)

        Args:
            topic: 글 주제
            content_type: 글 유형
            category: 카테고리
            keywords: 키워드 목록

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

    async def publish(self, topic_id: str) -> PipelineResult:
        """승인된 글을 양 플랫폼에 병렬 발행

        Args:
            topic_id: 발행할 주제 ID

        Returns:
            PipelineResult: 발행 결과가 포함된 결과
        """
        from database.repository import ContentRepository
        from database.models import TopicStatus
        from publishers.naver_publisher import NaverPublisher
        from publishers.tistory_publisher import TistoryPublisher

        if not self.db:
            raise RuntimeError("발행에는 db_manager가 필요합니다")

        repo = ContentRepository(self.db)
        contents = repo.get_contents_by_topic(topic_id)

        naver_content = None
        tistory_content = None
        for c in contents:
            if c.platform == "naver":
                naver_content = c
            elif c.platform == "tistory":
                tistory_content = c

        if not naver_content or not tistory_content:
            raise ValueError(
                f"주제 {topic_id}의 콘텐츠를 찾을 수 없습니다"
            )

        self.logger.info("pipeline.publish.start", topic_id=topic_id)

        # 양 플랫폼 병렬 발행
        naver_pub = NaverPublisher()
        tistory_pub = TistoryPublisher()

        naver_seo_detail = naver_content.seo_detail or {}
        tistory_seo_detail = tistory_content.seo_detail or {}

        naver_result, tistory_result = await asyncio.gather(
            naver_pub.publish(
                title=naver_content.title,
                content_html=naver_content.body,
                tags=naver_seo_detail.get("tags", []),
            ),
            tistory_pub.publish(
                title=tistory_content.title,
                content=tistory_content.body,
                tags=tistory_seo_detail.get("tags", []),
            ),
        )

        # DB 업데이트
        if naver_result.success and naver_result.published_url:
            repo.update_content_published(
                naver_content.id, naver_result.published_url
            )
        if tistory_result.success and tistory_result.published_url:
            repo.update_content_published(
                tistory_content.id, tistory_result.published_url
            )

        # 양쪽 다 성공하면 주제 상태 업데이트
        if naver_result.success and tistory_result.success:
            repo.update_topic_status(topic_id, TopicStatus.PUBLISHED)
            status = "published"
        else:
            status = "publish_partial"

        # 텔레그램 발행 완료 알림
        if self.notifier:
            await self._notify_publish_result(
                topic_id, naver_result, tistory_result
            )

        self.logger.info(
            "pipeline.publish.complete",
            topic_id=topic_id,
            naver_success=naver_result.success,
            tistory_success=tistory_result.success,
        )

        # 최소한의 PipelineResult 반환 (발행 전용)
        topic = repo.get_topic(topic_id)
        topic_pkg = TopicPackage(
            topic_id=topic_id,
            title=topic.title if topic else "",
            keywords=topic.keywords or [],
            category=topic.category or "",
            content_type=topic.content_type or "",
            source=topic.source or "",
            curator_score=topic.curator_score or 0.0,
        )

        # 발행 전용이라 draft/edit/seo 등은 더미
        from agents.data_models import (
            PlatformOutline, SectionOutline,
        )
        dummy_outline = SplitOutlines(
            topic_id=topic_id,
            naver=PlatformOutline(
                title_candidates=[], sections=[], target_length=(0, 0),
            ),
            tistory=PlatformOutline(
                title_candidates=[], sections=[], target_length=(0, 0),
            ),
        )
        dummy_draft = PlatformDraft(
            content_id="", topic_id=topic_id,
            platform="", title="", body="", word_count=0,
        )
        dummy_edit = EditResult(
            content_id="", platform="",
            final_draft="", quality_score=0.0,
            quality_detail={}, edit_summary={}, passed=False,
        )

        return PipelineResult(
            topic=topic_pkg,
            research=ResearchNote(topic_id=topic_id),
            outlines=dummy_outline,
            naver_draft=dummy_draft,
            tistory_draft=dummy_draft,
            naver_edited=dummy_edit,
            tistory_edited=dummy_edit,
            naver_content_id=naver_content.id,
            tistory_content_id=tistory_content.id,
            naver_publish_result=naver_result,
            tistory_publish_result=tistory_result,
            status=status,
        )

    async def _notify_publish_result(
        self,
        topic_id: str,
        naver_result: PublishResult,
        tistory_result: PublishResult,
    ) -> None:
        """발행 결과 텔레그램 알림"""
        lines = [f"<b>발행 완료</b> (주제: {topic_id})"]

        if naver_result.success:
            lines.append(
                f"  네이버: {naver_result.published_url}"
            )
        else:
            lines.append(f"  네이버: 실패 - {naver_result.error}")

        if tistory_result.success:
            lines.append(
                f"  티스토리: {tistory_result.published_url}"
            )
        else:
            lines.append(
                f"  티스토리: 실패 - {tistory_result.error}"
            )

        await self.notifier.send_message("\n".join(lines))
