"""
HNCollector — Hacker News Algolia API 기반 수집기
AI/ML 관련 키워드로 검색하고, 포인트 기준 필터링합니다.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
import structlog
import yaml

from agents.data_models import RawTopicData

logger = structlog.get_logger()

# httpx 공통 타임아웃
HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class HNCollector:
    """Hacker News Algolia API 수집기

    Args:
        min_points: 최소 포인트 (기본 50)
        keywords: 필터링 키워드. None이면 YAML에서 로드.
    """

    API_URL = "https://hn.algolia.com/api/v1/search"

    def __init__(
        self,
        min_points: int = 50,
        keywords: Optional[list[str]] = None,
    ):
        self.min_points = min_points
        self.keywords = keywords or self._load_keywords()
        self.logger = logger.bind(module="hn_collector")

    def _load_keywords(self) -> list[str]:
        """data_sources.yaml의 filtering_keywords 로드

        Returns:
            키워드 리스트
        """
        config_path = Path("config/data_sources.yaml")
        if not config_path.exists():
            return ["AI", "GPT", "LLM"]

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        communities = (
            data.get("overseas_sources", {})
            .get("communities", {})
            .get("sources", [])
        )
        for src in communities:
            if src.get("name") == "Hacker News":
                return src.get("filtering_keywords", ["AI", "GPT", "LLM"])

        return ["AI", "GPT", "LLM"]

    async def collect_all(self) -> list[RawTopicData]:
        """키워드별 검색 → 포인트 필터 → 중복 제거

        Returns:
            수집된 RawTopicData 리스트
        """
        all_items: list[RawTopicData] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            for keyword in self.keywords:
                try:
                    hits = await self._search(client, keyword)
                    for hit in hits:
                        obj_id = hit.get("objectID", "")
                        if obj_id in seen_ids:
                            continue
                        seen_ids.add(obj_id)

                        item = self._hit_to_raw_topic(hit)
                        if item:
                            all_items.append(item)
                except Exception as e:
                    self.logger.error(
                        "hn_collector.keyword_failed",
                        keyword=keyword,
                        error=str(e),
                    )

        self.logger.info(
            "hn_collector.collect_all_done",
            total=len(all_items),
            keywords_count=len(self.keywords),
        )
        return all_items

    async def _search(
        self, client: httpx.AsyncClient, query: str,
    ) -> list[dict]:
        """Algolia API 호출

        Args:
            client: httpx 클라이언트
            query: 검색 키워드

        Returns:
            API 응답의 hits 리스트
        """
        params = {
            "tags": "story",
            "query": query,
            "numericFilters": f"points>{self.min_points}",
            "hitsPerPage": 30,
        }
        url = f"{self.API_URL}?{urlencode(params)}"

        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        return data.get("hits", [])

    def _hit_to_raw_topic(self, hit: dict) -> Optional[RawTopicData]:
        """Algolia 검색 결과 → RawTopicData 변환

        Args:
            hit: Algolia API 응답 항목

        Returns:
            RawTopicData 또는 None
        """
        title = hit.get("title")
        if not title:
            return None

        url = hit.get("url") or (
            f"https://news.ycombinator.com/item?id="
            f"{hit.get('objectID', '')}"
        )

        published_at = None
        created_at_i = hit.get("created_at_i")
        if created_at_i:
            try:
                published_at = datetime.fromtimestamp(created_at_i)
            except (TypeError, ValueError, OSError):
                pass

        summary = (hit.get("story_text") or "")[:200]

        return RawTopicData(
            title=title,
            url=url,
            source="Hacker News",
            source_type="community",
            summary=summary,
            language="en",
            published_at=published_at,
        )
