"""
Pipeline 발행 로직 — 승인된 글을 양 플랫폼에 병렬 발행
pipeline.py에서 분리된 publish 관련 메서드를 담당합니다.
"""

import asyncio
from typing import Optional

import structlog

from agents.data_models import (
    TopicPackage,
    ResearchNote,
    SplitOutlines,
    PlatformOutline,
    PlatformDraft,
    EditResult,
    SEOResult,
    PublishResult,
)

logger = structlog.get_logger()


class PublishMixin:
    """Pipeline의 발행 관련 메서드를 제공하는 Mixin

    Pipeline 클래스에서 다중 상속으로 사용됩니다.
    self.db, self.notifier, self.logger를 필요로 합니다.
    """

    async def publish(self, topic_id: str):
        """승인된 글을 양 플랫폼에 병렬 발행

        Args:
            topic_id: 발행할 주제 ID

        Returns:
            PipelineResult: 발행 결과가 포함된 결과
        """
        from database.repository import ContentRepository
        from database.models import TopicStatus

        # 순환 import 방지: PipelineResult는 런타임에 로드
        from pipeline import PipelineResult

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

        if naver_result.success and tistory_result.success:
            repo.update_topic_status(topic_id, TopicStatus.PUBLISHED)
            status = "published"
        else:
            status = "publish_partial"

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

        # 최소한의 PipelineResult 반환
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

        dummy_outline = SplitOutlines(
            topic_id=topic_id,
            naver=PlatformOutline(
                title_candidates=[], sections=[],
                target_length=(0, 0),
            ),
            tistory=PlatformOutline(
                title_candidates=[], sections=[],
                target_length=(0, 0),
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
