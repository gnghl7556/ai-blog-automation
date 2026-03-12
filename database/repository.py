"""
ContentRepository — DB CRUD 레이어
Pydantic 모델 <-> SQLAlchemy 모델 매핑을 담당합니다.
RawTopic 관련 메서드는 RawTopicRepository에서 상속됩니다.
"""

import uuid
from datetime import datetime
from typing import Optional

import structlog

from database.session import DatabaseManager
from database.models import (
    Topic,
    Content,
    ApprovalLog,
    TopicStatus,
)
from database.raw_topic_repo import RawTopicRepository
from agents.data_models import (
    TopicPackage,
    EditResult,
    SEOResult,
)

logger = structlog.get_logger()


class ContentRepository(RawTopicRepository):
    """콘텐츠 DB 저장·조회 레이어

    RawTopicRepository를 상속하여 Topic/Content/ApprovalLog CRUD와
    RawTopic CRUD를 모두 제공합니다.

    Args:
        db: DatabaseManager 인스턴스
    """

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        self.logger = logger.bind(module="repository")

    # ── Topic ──

    def save_topic(self, topic_pkg: TopicPackage) -> str:
        """TopicPackage를 DB에 저장

        Args:
            topic_pkg: 파이프라인의 TopicPackage

        Returns:
            저장된 topic_id
        """
        with self.db.get_session() as session:
            topic = Topic(
                id=topic_pkg.topic_id,
                title=topic_pkg.title,
                title_ko=topic_pkg.title_ko,
                keywords=topic_pkg.keywords,
                category=topic_pkg.category,
                sub_category=topic_pkg.sub_category,
                content_type=topic_pkg.content_type,
                source=topic_pkg.source,
                source_url=topic_pkg.source_url,
                curator_score=topic_pkg.curator_score,
                status=TopicStatus.WRITING.value,
            )
            session.add(topic)

        self.logger.info(
            "repository.topic_saved",
            topic_id=topic_pkg.topic_id,
        )
        return topic_pkg.topic_id

    def update_topic_status(
        self, topic_id: str, status: TopicStatus
    ) -> None:
        """주제 상태 업데이트

        Args:
            topic_id: 주제 ID
            status: 새 상태
        """
        with self.db.get_session() as session:
            topic = session.query(Topic).filter_by(id=topic_id).first()
            if topic:
                topic.status = status.value
                topic.updated_at = datetime.utcnow()

        self.logger.info(
            "repository.topic_status_updated",
            topic_id=topic_id,
            status=status.value,
        )

    # ── Content ──

    def save_content(
        self,
        topic_id: str,
        platform: str,
        edit_result: EditResult,
        seo_result: SEOResult,
        body_final: str,
    ) -> str:
        """콘텐츠를 DB에 저장

        Args:
            topic_id: 주제 ID
            platform: 플랫폼 ("naver" / "tistory")
            edit_result: 편집 에이전트 결과
            seo_result: SEO 에이전트 결과
            body_final: 포맷 변환된 최종 본문

        Returns:
            저장된 content_id
        """
        content_id = uuid.uuid4().hex[:12]

        with self.db.get_session() as session:
            content = Content(
                id=content_id,
                topic_id=topic_id,
                platform=platform,
                title=seo_result.title_final,
                body=body_final,
                word_count=len(body_final),
                quality_score=edit_result.quality_score,
                quality_detail=edit_result.quality_detail,
                seo_score=seo_result.seo_score,
                seo_detail={
                    "tags": seo_result.tags,
                    "meta_description": seo_result.meta_description,
                },
                status="draft",
            )
            session.add(content)

        self.logger.info(
            "repository.content_saved",
            content_id=content_id,
            topic_id=topic_id,
            platform=platform,
        )
        return content_id

    def update_content_published(
        self, content_id: str, url: str
    ) -> None:
        """발행 완료 후 URL·상태 업데이트

        Args:
            content_id: 콘텐츠 ID
            url: 발행된 URL
        """
        with self.db.get_session() as session:
            content = (
                session.query(Content).filter_by(id=content_id).first()
            )
            if content:
                content.published_url = url
                content.published_at = datetime.utcnow()
                content.status = "published"
                content.updated_at = datetime.utcnow()

        self.logger.info(
            "repository.content_published",
            content_id=content_id,
            url=url,
        )

    # ── ApprovalLog ──

    def save_approval_log(
        self,
        content_id: str,
        action: str,
        notes: str = "",
    ) -> str:
        """승인/수정/반려 로그 저장

        Args:
            content_id: 콘텐츠 ID
            action: 승인 액션 ("approved" / "revised" / "rejected")
            notes: 비고

        Returns:
            저장된 로그 ID
        """
        log_id = uuid.uuid4().hex[:12]

        with self.db.get_session() as session:
            log = ApprovalLog(
                id=log_id,
                content_id=content_id,
                action=action,
                revision_notes=notes if action == "revised" else None,
                rejection_reason=notes if action == "rejected" else None,
            )
            session.add(log)

        self.logger.info(
            "repository.approval_logged",
            log_id=log_id,
            content_id=content_id,
            action=action,
        )
        return log_id

    # ── 조회 ──

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        """주제 조회"""
        with self.db.get_session() as session:
            topic = session.query(Topic).filter_by(id=topic_id).first()
            if topic:
                session.expunge(topic)
            return topic

    def get_topics_by_status(self, status: str) -> list[Topic]:
        """상태별 주제 목록 조회"""
        with self.db.get_session() as session:
            topics = (
                session.query(Topic).filter_by(status=status).all()
            )
            for t in topics:
                session.expunge(t)
            return topics

    def get_contents_by_topic(self, topic_id: str) -> list[Content]:
        """주제의 콘텐츠 목록 조회"""
        with self.db.get_session() as session:
            contents = (
                session.query(Content)
                .filter_by(topic_id=topic_id)
                .all()
            )
            for c in contents:
                session.expunge(c)
            return contents

    def get_all_topics(self) -> list[Topic]:
        """전체 주제 목록 조회 (최신순)"""
        with self.db.get_session() as session:
            topics = (
                session.query(Topic)
                .order_by(Topic.created_at.desc())
                .all()
            )
            for t in topics:
                session.expunge(t)
            return topics
