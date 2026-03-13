"""
CollectorOrchestrator — 수집기 통합 오케스트레이터
모든 수집기를 병렬 실행하고, 개별 실패를 격리합니다.
"""

import asyncio
from typing import Union

import structlog

from agents.data_models import RawTopicData, TrendData
from collectors.hn_collector import HNCollector
from collectors.reddit_collector import RedditCollector
from collectors.rss_collector import RSSCollector
from collectors.trend_collector import TrendCollector
from collectors.web_scraper import WebScraper

logger = structlog.get_logger()


class CollectorOrchestrator:
    """수집기 통합 오케스트레이터

    모든 수집기를 asyncio.gather로 병렬 실행하고
    개별 수집기 실패 시 나머지는 계속 진행합니다.
    """

    def __init__(self):
        self.logger = logger.bind(
            module="collector_orchestrator",
        )

    async def collect_all(self) -> list[RawTopicData]:
        """전체 수집 실행 (RSS + HN + Reddit + Web)

        Returns:
            모든 수집기 결과 통합 리스트
        """
        collectors: dict[str, object] = {
            "rss": RSSCollector(),
            "hn": HNCollector(),
            "reddit": RedditCollector(),
            "web": WebScraper(),
        }

        tasks = {
            name: coll.collect_all()
            for name, coll in collectors.items()
        }

        results = await asyncio.gather(
            *tasks.values(), return_exceptions=True,
        )

        all_items: list[RawTopicData] = []
        stats: dict[str, Union[int, str]] = {}

        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                self.logger.error(
                    "orchestrator.collector_failed",
                    collector=name,
                    error=str(result),
                    error_type=type(result).__name__,
                )
                stats[name] = f"error: {type(result).__name__}"
            else:
                all_items.extend(result)
                stats[name] = len(result)

        self.logger.info(
            "orchestrator.collect_all_done",
            total=len(all_items),
            **stats,
        )
        return all_items

    async def collect_trends(self) -> list[TrendData]:
        """트렌드 수집 (별도 스케줄)

        Returns:
            TrendData 리스트
        """
        collector = TrendCollector()
        try:
            results = await collector.collect_all()
            self.logger.info(
                "orchestrator.trends_done",
                count=len(results),
            )
            return results
        except Exception as e:
            self.logger.error(
                "orchestrator.trend_failed",
                error=str(e),
            )
            return []
