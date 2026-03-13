"""
Phase 7 — 데이터 소스 확장 수집기 테스트
HN, Reddit, WebScraper, TrendCollector, CollectorOrchestrator
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.data_models import RawTopicData, TrendData


# ── HNCollector ──


class TestHNCollector:
    """HN Algolia API 수집기 테스트"""

    @pytest.mark.asyncio
    async def test_collect_all_success(self):
        """정상 수집"""
        from collectors.hn_collector import HNCollector

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "hits": [
                {
                    "objectID": "123",
                    "title": "New AI Model Released",
                    "url": "https://example.com/ai",
                    "points": 100,
                    "created_at_i": 1710300000,
                    "story_text": "",
                },
                {
                    "objectID": "456",
                    "title": "GPT-5 Announced",
                    "url": "https://example.com/gpt5",
                    "points": 200,
                    "created_at_i": 1710300100,
                    "story_text": "Summary text",
                },
            ]
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.hn_collector.httpx.AsyncClient",
                    return_value=mock_client):
            collector = HNCollector(
                keywords=["AI"], min_points=50,
            )
            items = await collector.collect_all()

        assert len(items) == 2
        assert all(isinstance(i, RawTopicData) for i in items)
        assert items[0].source == "Hacker News"
        assert items[0].source_type == "community"

    @pytest.mark.asyncio
    async def test_collect_all_empty(self):
        """빈 결과"""
        from collectors.hn_collector import HNCollector

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"hits": []}

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.hn_collector.httpx.AsyncClient",
                    return_value=mock_client):
            collector = HNCollector(keywords=["AI"])
            items = await collector.collect_all()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """API 에러 시 빈 리스트 반환"""
        from collectors.hn_collector import HNCollector

        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            side_effect=Exception("Connection error")
        )
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.hn_collector.httpx.AsyncClient",
                    return_value=mock_client):
            collector = HNCollector(keywords=["AI"])
            items = await collector.collect_all()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_dedup_across_keywords(self):
        """키워드 간 중복 제거"""
        from collectors.hn_collector import HNCollector

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "hits": [
                {
                    "objectID": "same-id",
                    "title": "Same Article",
                    "url": "https://example.com/same",
                    "created_at_i": 1710300000,
                },
            ]
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.hn_collector.httpx.AsyncClient",
                    return_value=mock_client):
            collector = HNCollector(keywords=["AI", "GPT"])
            items = await collector.collect_all()

        assert len(items) == 1

    def test_hit_without_url(self):
        """URL 없는 hit → HN 링크 사용"""
        from collectors.hn_collector import HNCollector

        collector = HNCollector(keywords=["AI"])
        hit = {
            "objectID": "789",
            "title": "Ask HN: AI Tools",
            "url": None,
            "created_at_i": 1710300000,
        }
        item = collector._hit_to_raw_topic(hit)

        assert item is not None
        assert "news.ycombinator.com" in item.url


# ── RedditCollector ──


class TestRedditCollector:
    """Reddit JSON API 수집기 테스트"""

    def _make_post(
        self, title: str, url: str, subreddit: str = "ChatGPT",
    ) -> dict:
        return {
            "kind": "t3",
            "data": {
                "title": title,
                "url": url,
                "permalink": f"/r/{subreddit}/comments/abc/",
                "selftext": "Some discussion",
                "created_utc": 1710300000,
            },
        }

    @pytest.mark.asyncio
    async def test_collect_all_success(self):
        """정상 수집"""
        from collectors.reddit_collector import RedditCollector

        post = self._make_post(
            "ChatGPT Tips", "https://example.com/tips",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {"children": [post]}
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.reddit_collector.httpx.AsyncClient",
                    return_value=mock_client):
            collector = RedditCollector(subreddits=["ChatGPT"])
            items = await collector.collect_all()

        assert len(items) > 0
        assert items[0].source == "Reddit - r/ChatGPT"
        assert items[0].source_type == "community"

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """429 응답 시 대기 후 재시도"""
        from collectors.reddit_collector import RedditCollector

        rate_limited = MagicMock()
        rate_limited.status_code = 429

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()
        ok_response.json.return_value = {
            "data": {"children": []}
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            side_effect=[rate_limited, ok_response]
        )
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.reddit_collector.httpx.AsyncClient",
                    return_value=mock_client), \
             patch("collectors.reddit_collector.asyncio.sleep",
                    new_callable=AsyncMock):
            collector = RedditCollector(subreddits=["test"])
            items = await collector.collect_all()

        assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_subreddit_failure_isolation(self):
        """서브레딧 실패 시 나머지 계속"""
        from collectors.reddit_collector import RedditCollector

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Network error")
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "data": {"children": []}
            }
            return resp

        mock_client = MagicMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("collectors.reddit_collector.httpx.AsyncClient",
                    return_value=mock_client), \
             patch("collectors.reddit_collector.asyncio.sleep",
                    new_callable=AsyncMock):
            collector = RedditCollector(
                subreddits=["fail_sub", "ok_sub"],
            )
            items = await collector.collect_all()

        assert isinstance(items, list)

    def test_post_to_raw_topic(self):
        """포스트 → RawTopicData 변환"""
        from collectors.reddit_collector import RedditCollector

        collector = RedditCollector()
        post = self._make_post(
            "Test Post", "https://example.com/test",
        )
        item = collector._post_to_raw_topic(post, "ChatGPT")

        assert item.title == "Test Post"
        assert item.source == "Reddit - r/ChatGPT"
        assert item.published_at is not None


# ── WebScraper ──


class TestWebScraper:
    """웹 스크래퍼 테스트"""

    @pytest.mark.asyncio
    async def test_scrape_site_success(self):
        """정상 스크래핑"""
        from collectors.web_scraper import WebScraper

        html = """
        <html><body>
            <a href="/news/article1">
                <h3>AI Safety Update</h3>
            </a>
            <a href="/news/article2">
                <h3>Claude 4 Released</h3>
            </a>
        </body></html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        sites = [
            {
                "name": "Anthropic News",
                "url": "https://www.anthropic.com/news",
                "article_selector": "a[href*='/news/']",
                "title_selector": "h3",
                "link_attr": "href",
                "base_url": "https://www.anthropic.com",
                "language": "en",
                "source_type": "blog",
                "max_items": 20,
            }
        ]

        with patch("collectors.web_scraper.httpx.AsyncClient",
                    return_value=mock_client):
            scraper = WebScraper(sites=sites)
            items = await scraper.collect_all()

        assert len(items) == 2
        assert items[0].title == "AI Safety Update"
        assert items[0].source == "Anthropic News"
        assert "anthropic.com" in items[0].url

    @pytest.mark.asyncio
    async def test_empty_results_warning(self):
        """결과 0건 시 경고"""
        from collectors.web_scraper import WebScraper

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.text = "<html><body></body></html>"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        sites = [
            {
                "name": "Test",
                "url": "https://example.com",
                "article_selector": ".article",
                "title_selector": "h3",
                "link_attr": "href",
                "base_url": "https://example.com",
                "source_type": "blog",
            }
        ]

        with patch("collectors.web_scraper.httpx.AsyncClient",
                    return_value=mock_client):
            scraper = WebScraper(sites=sites)
            items = await scraper.collect_all()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_relative_url_resolution(self):
        """상대 경로 → 절대 경로 변환"""
        from collectors.web_scraper import WebScraper

        html = '<a href="/blog/post1"><h3>Post</h3></a>'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(
            return_value=mock_client
        )
        mock_client.__aexit__ = AsyncMock(return_value=False)

        sites = [
            {
                "name": "Test",
                "url": "https://example.com/blog",
                "article_selector": "a",
                "title_selector": "h3",
                "link_attr": "href",
                "base_url": "https://example.com",
                "source_type": "blog",
            }
        ]

        with patch("collectors.web_scraper.httpx.AsyncClient",
                    return_value=mock_client):
            scraper = WebScraper(sites=sites)
            items = await scraper.collect_all()

        assert len(items) == 1
        assert items[0].url == "https://example.com/blog/post1"

    @pytest.mark.asyncio
    async def test_missing_config(self):
        """설정 없으면 빈 리스트"""
        from collectors.web_scraper import WebScraper

        scraper = WebScraper(
            config_path="/nonexistent/scrapers.yaml",
        )
        items = await scraper.collect_all()
        assert len(items) == 0


# ── TrendCollector ──


class TestTrendCollector:
    """트렌드 수집기 테스트"""

    @pytest.mark.asyncio
    async def test_google_trends_success(self):
        """Google Trends 정상 수집"""
        from collectors.trend_collector import TrendCollector

        keywords_config = [
            {"category": "AI", "keywords": ["ChatGPT", "AI"]}
        ]

        mock_trends = [
            TrendData(
                keyword="ChatGPT",
                source="google_trends",
                score=85.0,
                category="AI",
            ),
        ]

        collector = TrendCollector(
            keywords_config=keywords_config,
        )
        with patch.object(
            collector, "_collect_google_trends",
            new_callable=AsyncMock,
            return_value=mock_trends,
        ):
            results = await collector.collect_all()

        assert len(results) == 1
        assert results[0].keyword == "ChatGPT"
        assert results[0].source == "google_trends"

    @pytest.mark.asyncio
    async def test_naver_optional(self, monkeypatch):
        """네이버 키 없으면 스킵"""
        from collectors.trend_collector import TrendCollector

        monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

        collector = TrendCollector(
            keywords_config=[
                {"category": "AI", "keywords": ["AI"]}
            ],
        )

        with patch.object(
            collector, "_collect_google_trends",
            new_callable=AsyncMock,
            return_value=[],
        ):
            results = await collector.collect_all()

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_pytrends_blocked(self):
        """pytrends 차단 시 빈 리스트"""
        from collectors.trend_collector import TrendCollector

        collector = TrendCollector(
            keywords_config=[
                {"category": "AI", "keywords": ["AI"]}
            ],
        )

        with patch.object(
            collector, "_collect_google_trends",
            new_callable=AsyncMock,
            side_effect=Exception("429 Too Many Requests"),
        ):
            results = await collector.collect_all()

        assert isinstance(results, list)


# ── CollectorOrchestrator ──


class TestCollectorOrchestrator:
    """오케스트레이터 테스트"""

    @pytest.mark.asyncio
    async def test_all_success(self):
        """전체 수집기 성공"""
        from collectors.collector_orchestrator import (
            CollectorOrchestrator,
        )

        rss_items = [
            RawTopicData(
                title="RSS Article",
                url="https://example.com/rss",
                source="Test RSS",
            )
        ]
        hn_items = [
            RawTopicData(
                title="HN Article",
                url="https://example.com/hn",
                source="Hacker News",
            )
        ]

        with patch(
            "collectors.collector_orchestrator.RSSCollector"
        ) as mock_rss, patch(
            "collectors.collector_orchestrator.HNCollector"
        ) as mock_hn, patch(
            "collectors.collector_orchestrator.RedditCollector"
        ) as mock_reddit, patch(
            "collectors.collector_orchestrator.WebScraper"
        ) as mock_web:
            mock_rss.return_value.collect_all = AsyncMock(
                return_value=rss_items
            )
            mock_hn.return_value.collect_all = AsyncMock(
                return_value=hn_items
            )
            mock_reddit.return_value.collect_all = AsyncMock(
                return_value=[]
            )
            mock_web.return_value.collect_all = AsyncMock(
                return_value=[]
            )

            orch = CollectorOrchestrator()
            items = await orch.collect_all()

        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        """일부 수집기 실패 시 나머지 결과 반환"""
        from collectors.collector_orchestrator import (
            CollectorOrchestrator,
        )

        rss_items = [
            RawTopicData(
                title="RSS OK",
                url="https://example.com/ok",
                source="RSS",
            )
        ]

        with patch(
            "collectors.collector_orchestrator.RSSCollector"
        ) as mock_rss, patch(
            "collectors.collector_orchestrator.HNCollector"
        ) as mock_hn, patch(
            "collectors.collector_orchestrator.RedditCollector"
        ) as mock_reddit, patch(
            "collectors.collector_orchestrator.WebScraper"
        ) as mock_web:
            mock_rss.return_value.collect_all = AsyncMock(
                return_value=rss_items
            )
            mock_hn.return_value.collect_all = AsyncMock(
                side_effect=Exception("HN API down")
            )
            mock_reddit.return_value.collect_all = AsyncMock(
                side_effect=Exception("Reddit timeout")
            )
            mock_web.return_value.collect_all = AsyncMock(
                return_value=[]
            )

            orch = CollectorOrchestrator()
            items = await orch.collect_all()

        assert len(items) == 1
        assert items[0].title == "RSS OK"

    @pytest.mark.asyncio
    async def test_all_failure(self):
        """전체 수집기 실패 시 빈 리스트"""
        from collectors.collector_orchestrator import (
            CollectorOrchestrator,
        )

        with patch(
            "collectors.collector_orchestrator.RSSCollector"
        ) as mock_rss, patch(
            "collectors.collector_orchestrator.HNCollector"
        ) as mock_hn, patch(
            "collectors.collector_orchestrator.RedditCollector"
        ) as mock_reddit, patch(
            "collectors.collector_orchestrator.WebScraper"
        ) as mock_web:
            for m in [mock_rss, mock_hn, mock_reddit, mock_web]:
                m.return_value.collect_all = AsyncMock(
                    side_effect=Exception("fail")
                )

            orch = CollectorOrchestrator()
            items = await orch.collect_all()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_collect_trends(self):
        """트렌드 수집"""
        from collectors.collector_orchestrator import (
            CollectorOrchestrator,
        )

        trend_items = [
            TrendData(
                keyword="ChatGPT",
                source="google_trends",
                score=90.0,
                category="AI",
            )
        ]

        with patch(
            "collectors.collector_orchestrator.TrendCollector"
        ) as mock_trend:
            mock_trend.return_value.collect_all = AsyncMock(
                return_value=trend_items
            )

            orch = CollectorOrchestrator()
            trends = await orch.collect_trends()

        assert len(trends) == 1
        assert trends[0].keyword == "ChatGPT"


# ── TrendData 모델 ──


class TestTrendDataModel:
    """TrendData Pydantic 모델 테스트"""

    def test_create(self):
        """생성"""
        td = TrendData(
            keyword="AI",
            source="google_trends",
            score=75.5,
            category="AI 서비스",
        )
        assert td.keyword == "AI"
        assert td.source == "google_trends"
        assert td.score == 75.5
        assert td.collected_at is not None

    def test_serialization(self):
        """직렬화"""
        td = TrendData(
            keyword="GPT",
            source="naver_datalab",
            score=42.0,
            category="AI 개념",
        )
        data = td.model_dump()
        assert data["keyword"] == "GPT"
        assert data["source"] == "naver_datalab"
