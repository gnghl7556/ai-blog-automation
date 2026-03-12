"""
RawTopicRepository — RawTopic 관련 DB CRUD
Phase 4 (수집/큐레이션) + Phase 5 (정리/통계) 전용 메서드
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog

from database.session import DatabaseManager
from database.models import (
    RawTopic,
    Topic,
    TopicStatus,
)
from agents.data_models import (
    RawTopicData,
    CurationResult,
)

logger = structlog.get_logger()


class RawTopicRepository:
    """RawTopic DB 저장·조회 레이어

    Args:
        db: DatabaseManager 인스턴스
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.logger = logger.bind(module="raw_topic_repo")

    def save_raw_topics(self, items: list[RawTopicData]) -> int:
        """RawTopicData 리스트를 DB에 저장

        URL unique 충돌 시 해당 항목은 스킵합니다.

        Args:
            items: 저장할 RawTopicData 리스트

        Returns:
            저장된 항목 수
        """
        saved = 0
        for item in items:
            raw_id = uuid.uuid4().hex[:12]
            try:
                with self.db.get_session() as session:
                    raw = RawTopic(
                        id=raw_id,
                        title=item.title,
                        title_ko=item.title_ko,
                        url=item.url,
                        source=item.source,
                        source_type=item.source_type,
                        summary=item.summary,
                        summary_ko=item.summary_ko,
                        language=item.language,
                        published_at=item.published_at,
                        status="collected",
                    )
                    session.add(raw)
                saved += 1
            except Exception as e:
                self.logger.warning(
                    "repository.raw_topic_duplicate",
                    url=item.url,
                    error=str(e),
                )

        self.logger.info(
            "repository.raw_topics_saved",
            total=len(items),
            saved=saved,
        )
        return saved

    def get_raw_topics_by_status(
        self, status: str
    ) -> list[RawTopic]:
        """상태별 RawTopic 조회

        Args:
            status: collected / curated / selected / used / skipped

        Returns:
            RawTopic 리스트
        """
        with self.db.get_session() as session:
            raw_topics = (
                session.query(RawTopic)
                .filter_by(status=status)
                .order_by(RawTopic.collected_at.desc())
                .all()
            )
            for rt in raw_topics:
                session.expunge(rt)
            return raw_topics

    def update_raw_topic_curated(
        self, raw_id: str, result: CurationResult
    ) -> None:
        """큐레이션 결과 업데이트

        Args:
            raw_id: RawTopic ID
            result: CurationResult
        """
        with self.db.get_session() as session:
            raw = (
                session.query(RawTopic).filter_by(id=raw_id).first()
            )
            if raw:
                raw.curator_score = result.score
                raw.curator_reason = result.reason
                raw.curator_detail = result.criteria_scores
                raw.recommended_type = result.recommended_type
                raw.recommended_category = result.recommended_category
                raw.status = "selected" if result.selected else "skipped"

        self.logger.info(
            "repository.raw_topic_curated",
            raw_id=raw_id,
            score=result.score,
            selected=result.selected,
        )

    def mark_raw_topic_used(
        self, raw_id: str, topic_id: str
    ) -> None:
        """글 생성에 사용된 RawTopic 상태 업데이트

        Args:
            raw_id: RawTopic ID
            topic_id: 생성된 Topic ID
        """
        with self.db.get_session() as session:
            raw = (
                session.query(RawTopic).filter_by(id=raw_id).first()
            )
            if raw:
                raw.status = "used"
                raw.used_topic_id = topic_id

        self.logger.info(
            "repository.raw_topic_used",
            raw_id=raw_id,
            topic_id=topic_id,
        )

    def cleanup_old_raw_topics(
        self, retention_days: int = 30
    ) -> int:
        """retention_days보다 오래된 skipped/used raw_topics 삭제

        collected/selected 상태는 보존합니다.

        Args:
            retention_days: 보존 기간 (일 단위)

        Returns:
            삭제된 항목 수
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        with self.db.get_session() as session:
            deleted = (
                session.query(RawTopic)
                .filter(
                    RawTopic.status.in_(["skipped", "used"]),
                    RawTopic.collected_at < cutoff,
                )
                .delete(synchronize_session="fetch")
            )

        self.logger.info(
            "repository.cleanup_old_raw_topics",
            retention_days=retention_days,
            deleted=deleted,
        )
        return deleted

    def get_daily_stats(self) -> dict:
        """오늘(UTC 기준) 수집/큐레이션/생성/발행 통계

        Returns:
            통계 딕셔너리
        """
        from sqlalchemy import func

        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        with self.db.get_session() as session:
            collected = (
                session.query(func.count(RawTopic.id))
                .filter(RawTopic.collected_at >= today_start)
                .scalar()
            ) or 0

            curated = (
                session.query(func.count(RawTopic.id))
                .filter(
                    RawTopic.collected_at >= today_start,
                    RawTopic.status.in_(["selected", "skipped"]),
                )
                .scalar()
            ) or 0

            selected = (
                session.query(func.count(RawTopic.id))
                .filter(
                    RawTopic.collected_at >= today_start,
                    RawTopic.status == "selected",
                )
                .scalar()
            ) or 0

            generated = (
                session.query(func.count(Topic.id))
                .filter(Topic.created_at >= today_start)
                .scalar()
            ) or 0

            published = (
                session.query(func.count(Topic.id))
                .filter(
                    Topic.created_at >= today_start,
                    Topic.status == TopicStatus.PUBLISHED.value,
                )
                .scalar()
            ) or 0

            pending = (
                session.query(func.count(Topic.id))
                .filter(
                    Topic.status == TopicStatus.REVIEW.value,
                )
                .scalar()
            ) or 0

        return {
            "collected": collected,
            "curated": curated,
            "selected": selected,
            "generated": generated,
            "published": published,
            "pending": pending,
        }

    def get_recent_raw_topic_titles(
        self, days: int = 7
    ) -> list[tuple[str, str]]:
        """최근 N일 내 수집된 RawTopic 제목+URL 조회

        Args:
            days: 조회 범위 (일 단위)

        Returns:
            [(title, url), ...] 리스트
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        with self.db.get_session() as session:
            results = (
                session.query(RawTopic.title, RawTopic.url)
                .filter(RawTopic.collected_at >= cutoff)
                .all()
            )
            return [(r[0], r[1]) for r in results]
