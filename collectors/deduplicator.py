"""
Deduplicator — 수집된 주제의 중복을 제거하는 클래스
URL 정확 매칭 + 제목 유사도 80% 이상을 중복으로 판별합니다.
"""

import structlog

from agents.data_models import RawTopicData
from database.session import DatabaseManager
from database.repository import ContentRepository
from utils.text_utils import calculate_similarity

logger = structlog.get_logger()


class Deduplicator:
    """수집된 주제 중복 제거

    2단계 중복 체크:
    1. URL 정확 매칭 (DB + 배치 내)
    2. 제목 유사도 80% 이상 (최근 7일)

    Args:
        db: DatabaseManager 인스턴스
    """

    SIMILARITY_THRESHOLD = 0.8

    def __init__(self, db: DatabaseManager):
        self.repo = ContentRepository(db)
        self.logger = logger.bind(module="deduplicator")

    def deduplicate(
        self, items: list[RawTopicData]
    ) -> list[RawTopicData]:
        """중복 제거 실행

        Args:
            items: 수집된 RawTopicData 리스트

        Returns:
            중복이 제거된 RawTopicData 리스트
        """
        # 1. 배치 내 중복 제거
        batch_deduped = self._deduplicate_batch(items)

        # 2. DB 기존 데이터와 비교
        recent = self.repo.get_recent_raw_topic_titles(days=7)
        existing_urls = {url for _, url in recent}
        existing_titles = [title for title, _ in recent]

        result = []
        for item in batch_deduped:
            if item.url in existing_urls:
                self.logger.debug(
                    "deduplicator.url_match",
                    url=item.url,
                )
                continue

            if self._title_similar(item.title, existing_titles):
                self.logger.debug(
                    "deduplicator.title_similar",
                    title=item.title,
                )
                continue

            result.append(item)

        removed = len(items) - len(result)
        self.logger.info(
            "deduplicator.done",
            input=len(items),
            output=len(result),
            removed=removed,
        )
        return result

    def _deduplicate_batch(
        self, items: list[RawTopicData]
    ) -> list[RawTopicData]:
        """배치 내 중복 제거

        URL 기반 → 먼저 나온 항목 유지
        제목 유사도 기반 → source_type 'blog' 우선

        Args:
            items: 수집된 RawTopicData 리스트

        Returns:
            배치 내 중복이 제거된 리스트
        """
        seen_urls: set[str] = set()
        result: list[RawTopicData] = []

        for item in items:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)

            is_dup = False
            for existing in result:
                sim = calculate_similarity(item.title, existing.title)
                if sim >= self.SIMILARITY_THRESHOLD:
                    # blog 소스 우선 유지
                    if (
                        item.source_type == "blog"
                        and existing.source_type != "blog"
                    ):
                        result.remove(existing)
                        result.append(item)
                    is_dup = True
                    break

            if not is_dup:
                result.append(item)

        return result

    def _title_similar(
        self, title: str, existing_titles: list[str]
    ) -> bool:
        """기존 제목과 유사도 80% 이상인지 확인

        Args:
            title: 비교할 제목
            existing_titles: DB에 있는 기존 제목들

        Returns:
            유사한 제목이 있으면 True
        """
        for existing in existing_titles:
            if calculate_similarity(title, existing) >= self.SIMILARITY_THRESHOLD:
                return True
        return False
