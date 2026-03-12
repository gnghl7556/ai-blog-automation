"""
RSSCollector — RSS 피드에서 주제를 수집하는 수집기
config/data_sources.yaml에서 RSS 소스 목록을 로드하고,
feedparser로 각 피드를 파싱하여 RawTopicData 리스트를 반환합니다.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
import structlog
import feedparser

from agents.data_models import RawTopicData
from utils.text_utils import strip_html_tags

logger = structlog.get_logger()


class RSSCollector:
    """RSS 피드 수집기

    Args:
        sources: RSS 소스 설정 리스트. None이면 YAML에서 자동 로드.
    """

    def __init__(self, sources: Optional[list[dict]] = None):
        self.logger = logger.bind(module="rss_collector")
        if sources is not None:
            self.sources = sources
        else:
            self.sources = self._load_rss_sources()

    def _load_rss_sources(self) -> list[dict]:
        """data_sources.yaml에서 method=='rss'인 소스만 추출

        Returns:
            소스 설정 리스트
        """
        config_path = Path("config/data_sources.yaml")
        if not config_path.exists():
            self.logger.warning("rss_collector.config_not_found")
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rss_sources = []
        source_type_map = {
            "ai_company_blogs": "blog",
            "overseas_media": "media",
            "domestic_media": "media",
        }

        for section_key, section_type in source_type_map.items():
            # overseas_sources 또는 domestic_sources 하위 탐색
            for top_key in ("overseas_sources", "domestic_sources"):
                top = data.get(top_key, {})
                section = top.get(section_key, {})
                for src in section.get("sources", []):
                    if src.get("method") == "rss" and src.get("rss"):
                        rss_sources.append({
                            "name": src["name"],
                            "rss": src["rss"],
                            "language": src.get("language", "en"),
                            "keywords_filter": src.get(
                                "keywords_filter", []
                            ),
                            "source_type": section_type,
                        })

        self.logger.info(
            "rss_collector.sources_loaded",
            count=len(rss_sources),
        )
        return rss_sources

    async def collect_all(self) -> list[RawTopicData]:
        """모든 RSS 소스에서 주제 수집

        Returns:
            수집된 RawTopicData 리스트
        """
        all_items: list[RawTopicData] = []

        for source in self.sources:
            try:
                items = await self.collect_source(source)
                all_items.extend(items)
                self.logger.info(
                    "rss_collector.source_collected",
                    source=source["name"],
                    count=len(items),
                )
            except Exception as e:
                self.logger.error(
                    "rss_collector.source_failed",
                    source=source["name"],
                    error=str(e),
                )

        self.logger.info(
            "rss_collector.collect_all_done",
            total=len(all_items),
        )
        return all_items

    async def collect_source(
        self, source: dict
    ) -> list[RawTopicData]:
        """단일 소스에서 주제 수집

        Args:
            source: 소스 설정 딕셔너리

        Returns:
            해당 소스의 RawTopicData 리스트
        """
        entries = self._parse_feed(source["rss"])

        keywords = source.get("keywords_filter", [])
        if keywords:
            entries = self._apply_keyword_filter(entries, keywords)

        return [
            self._entry_to_raw_topic(entry, source)
            for entry in entries
        ]

    def _parse_feed(self, feed_url: str) -> list[dict]:
        """feedparser로 RSS 피드 파싱

        Args:
            feed_url: RSS 피드 URL

        Returns:
            feedparser 엔트리 리스트
        """
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            self.logger.warning(
                "rss_collector.feed_parse_error",
                url=feed_url,
                error=str(feed.bozo_exception),
            )
            return []

        return feed.entries

    def _apply_keyword_filter(
        self, entries: list[dict], keywords: list[str]
    ) -> list[dict]:
        """키워드 필터 적용

        Args:
            entries: feedparser 엔트리 리스트
            keywords: 필터링 키워드 (제목+요약에서 검색)

        Returns:
            필터링된 엔트리 리스트
        """
        if not keywords:
            return entries

        filtered = []
        for entry in entries:
            text = (
                entry.get("title", "")
                + " "
                + entry.get("summary", "")
            ).lower()
            if any(kw.lower() in text for kw in keywords):
                filtered.append(entry)

        return filtered

    def _entry_to_raw_topic(
        self, entry: dict, source: dict
    ) -> RawTopicData:
        """feedparser 엔트리를 RawTopicData로 변환

        Args:
            entry: feedparser 엔트리
            source: 소스 설정 딕셔너리

        Returns:
            RawTopicData
        """
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        summary = strip_html_tags(entry.get("summary", ""))

        return RawTopicData(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            source=source["name"],
            source_type=source.get("source_type", "media"),
            summary=summary,
            language=source.get("language", "en"),
            published_at=published_at,
        )
