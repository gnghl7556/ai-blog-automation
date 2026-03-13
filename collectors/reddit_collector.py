"""
RedditCollector — Reddit JSON API 기반 수집기
httpx로 공개 JSON API를 호출합니다 (PRAW 미사용, 의존성 최소화).
"""

import asyncio
import os
from datetime import datetime
from typing import Optional

import httpx
import structlog

from agents.data_models import RawTopicData

logger = structlog.get_logger()

HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class RedditCollector:
    """Reddit JSON API 수집기

    Args:
        subreddits: 대상 서브레딧 리스트
        user_agent: HTTP User-Agent 헤더
    """

    BASE_URL = "https://www.reddit.com/r"
    DEFAULT_SUBREDDITS = ["ChatGPT", "artificial", "MachineLearning"]

    def __init__(
        self,
        subreddits: Optional[list[str]] = None,
        user_agent: Optional[str] = None,
    ):
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS
        self.user_agent = (
            user_agent
            or os.environ.get(
                "REDDIT_USER_AGENT", "ai-blog-bot/1.0"
            )
        )
        self.logger = logger.bind(module="reddit_collector")

    async def collect_all(self) -> list[RawTopicData]:
        """전체 서브레딧 수집 (hot + top/day)

        서브레딧 간 1초 대기로 rate limit 방지.

        Returns:
            수집된 RawTopicData 리스트
        """
        all_items: list[RawTopicData] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            timeout=HTTPX_TIMEOUT,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        ) as client:
            for i, subreddit in enumerate(self.subreddits):
                if i > 0:
                    await asyncio.sleep(1.0)

                try:
                    items = await self._collect_subreddit(
                        client, subreddit, seen_urls,
                    )
                    all_items.extend(items)
                    self.logger.info(
                        "reddit_collector.subreddit_done",
                        subreddit=subreddit,
                        count=len(items),
                    )
                except Exception as e:
                    self.logger.error(
                        "reddit_collector.subreddit_failed",
                        subreddit=subreddit,
                        error=str(e),
                    )

        self.logger.info(
            "reddit_collector.collect_all_done",
            total=len(all_items),
        )
        return all_items

    async def _collect_subreddit(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
        seen_urls: set[str],
    ) -> list[RawTopicData]:
        """단일 서브레딧에서 hot + top/day 수집

        Args:
            client: httpx 클라이언트
            subreddit: 서브레딧 이름
            seen_urls: 중복 방지 URL 집합

        Returns:
            RawTopicData 리스트
        """
        items: list[RawTopicData] = []

        for sort, params in [
            ("hot", {"limit": "25"}),
            ("top", {"limit": "25", "t": "day"}),
        ]:
            posts = await self._fetch_listing(
                client, subreddit, sort, params,
            )
            for post in posts:
                item = self._post_to_raw_topic(post, subreddit)
                if item and item.url not in seen_urls:
                    seen_urls.add(item.url)
                    items.append(item)

            await asyncio.sleep(1.0)

        return items

    async def _fetch_listing(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
        sort: str,
        params: Optional[dict] = None,
    ) -> list[dict]:
        """Reddit JSON API 호출

        Args:
            client: httpx 클라이언트
            subreddit: 서브레딧 이름
            sort: 정렬 방식 (hot, top)
            params: 쿼리 파라미터

        Returns:
            포스트 데이터 리스트
        """
        url = f"{self.BASE_URL}/{subreddit}/{sort}.json"
        resp = await client.get(url, params=params)

        if resp.status_code == 429:
            self.logger.warning(
                "reddit_collector.rate_limited",
                subreddit=subreddit,
            )
            await asyncio.sleep(60)
            resp = await client.get(url, params=params)

        resp.raise_for_status()
        data = resp.json()

        children = data.get("data", {}).get("children", [])
        return [
            child for child in children
            if child.get("kind") == "t3"
        ]

    def _post_to_raw_topic(
        self, post: dict, subreddit: str,
    ) -> Optional[RawTopicData]:
        """Reddit 포스트 → RawTopicData 변환

        Args:
            post: Reddit API 포스트 데이터
            subreddit: 서브레딧 이름

        Returns:
            RawTopicData 또는 None
        """
        post_data = post.get("data", {})
        title = post_data.get("title")
        if not title:
            return None

        url = post_data.get("url", "")
        if not url or url.startswith("/"):
            permalink = post_data.get("permalink", "")
            url = f"https://www.reddit.com{permalink}"

        published_at = None
        created_utc = post_data.get("created_utc")
        if created_utc:
            try:
                published_at = datetime.fromtimestamp(created_utc)
            except (TypeError, ValueError, OSError):
                pass

        selftext = (post_data.get("selftext") or "")[:200]

        return RawTopicData(
            title=title,
            url=url,
            source=f"Reddit - r/{subreddit}",
            source_type="community",
            summary=selftext,
            language="en",
            published_at=published_at,
        )
