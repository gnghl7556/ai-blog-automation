"""
Phase 4 테스트 — RSS 수집, 중복 제거, 큐레이션, Repository
"""

import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.data_models import RawTopicData, CurationResult
from database.repository import ContentRepository
from database.models import RawTopic


# ── Fixtures ──

@pytest.fixture
def repo(db):
    return ContentRepository(db)


def _make_raw_topic(
    title="Test Title",
    url="https://example.com/1",
    source="TestSource",
    language="en",
    **kwargs,
) -> RawTopicData:
    return RawTopicData(
        title=title,
        url=url,
        source=source,
        source_type=kwargs.get("source_type", "media"),
        summary=kwargs.get("summary", "Test summary"),
        language=language,
        published_at=kwargs.get("published_at"),
        title_ko=kwargs.get("title_ko"),
        summary_ko=kwargs.get("summary_ko"),
    )


# ═══════════════════════════════════════════
# RSSCollector 테스트
# ═══════════════════════════════════════════

class TestRSSCollector:
    def test_load_rss_sources_from_yaml(self):
        """YAML에서 RSS 소스 로드"""
        from collectors.rss_collector import RSSCollector
        collector = RSSCollector()
        # data_sources.yaml이 존재하면 소스 로드
        assert isinstance(collector.sources, list)

    def test_entry_to_raw_topic(self):
        """feedparser 엔트리 → RawTopicData 변환"""
        from collectors.rss_collector import RSSCollector

        collector = RSSCollector(sources=[])
        entry = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "<p>Article summary</p>",
            "published_parsed": time.strptime(
                "2026-03-12", "%Y-%m-%d"
            ),
        }
        source = {
            "name": "Test Blog",
            "language": "en",
            "source_type": "blog",
        }

        result = collector._entry_to_raw_topic(entry, source)

        assert result.title == "Test Article"
        assert result.url == "https://example.com/article"
        assert result.source == "Test Blog"
        assert result.source_type == "blog"
        assert result.language == "en"
        assert "<p>" not in result.summary  # HTML 태그 제거

    def test_keyword_filter_applied(self):
        """키워드 필터 동작"""
        from collectors.rss_collector import RSSCollector

        collector = RSSCollector(sources=[])
        entries = [
            {"title": "AI Revolution", "summary": "About AI"},
            {"title": "Weather Report", "summary": "Sunny day"},
            {"title": "GPT Update", "summary": "New features"},
        ]

        filtered = collector._apply_keyword_filter(entries, ["AI", "GPT"])
        assert len(filtered) == 2

    def test_keyword_filter_empty_passes_all(self):
        """빈 키워드 필터는 전체 통과"""
        from collectors.rss_collector import RSSCollector

        collector = RSSCollector(sources=[])
        entries = [{"title": "Test", "summary": ""}]
        filtered = collector._apply_keyword_filter(entries, [])
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_collect_source_with_mock_feed(self):
        """mock feed로 소스 수집"""
        from collectors.rss_collector import RSSCollector

        collector = RSSCollector(sources=[])

        mock_entries = [
            {
                "title": "Article 1",
                "link": "https://example.com/1",
                "summary": "Summary 1",
            },
            {
                "title": "Article 2",
                "link": "https://example.com/2",
                "summary": "Summary 2",
            },
        ]

        with patch.object(
            collector, "_parse_feed", return_value=mock_entries
        ):
            source = {
                "name": "Mock Source",
                "rss": "https://mock.rss",
                "language": "en",
                "source_type": "media",
            }
            items = await collector.collect_source(source)

        assert len(items) == 2
        assert items[0].title == "Article 1"

    @pytest.mark.asyncio
    async def test_collect_source_error_returns_empty(self):
        """피드 파싱 실패 시 빈 리스트"""
        from collectors.rss_collector import RSSCollector

        collector = RSSCollector(sources=[])

        with patch.object(
            collector, "_parse_feed", side_effect=Exception("Network error")
        ):
            source = {
                "name": "Bad Source",
                "rss": "https://bad.rss",
                "language": "en",
            }
            # collect_all에서 에러 catch
            collector.sources = [source]
            items = await collector.collect_all()

        assert items == []


# ═══════════════════════════════════════════
# Deduplicator 테스트
# ═══════════════════════════════════════════

class TestDeduplicator:
    def test_url_exact_match_removed(self, db, repo):
        """같은 URL은 제거"""
        from collectors.deduplicator import Deduplicator

        # DB에 기존 항목 저장
        existing = _make_raw_topic(url="https://example.com/dup")
        repo.save_raw_topics([existing])

        dedup = Deduplicator(db)
        items = [
            _make_raw_topic(title="New Title", url="https://example.com/dup"),
            _make_raw_topic(title="Unique", url="https://example.com/unique"),
        ]
        result = dedup.deduplicate(items)

        assert len(result) == 1
        assert result[0].url == "https://example.com/unique"

    def test_title_similar_removed(self, db, repo):
        """제목 유사도 80% 이상은 제거"""
        from collectors.deduplicator import Deduplicator

        existing = _make_raw_topic(
            title="OpenAI Launches GPT-5 with Amazing Features",
            url="https://example.com/old",
        )
        repo.save_raw_topics([existing])

        dedup = Deduplicator(db)
        items = [
            _make_raw_topic(
                title="OpenAI Launches GPT-5 with Amazing New Features",
                url="https://example.com/new",
            ),
        ]
        result = dedup.deduplicate(items)

        assert len(result) == 0  # 유사도 높아서 제거됨

    def test_title_below_threshold_kept(self, db):
        """유사도 80% 미만은 유지"""
        from collectors.deduplicator import Deduplicator

        dedup = Deduplicator(db)
        items = [
            _make_raw_topic(title="AI Revolution", url="https://a.com/1"),
            _make_raw_topic(title="Cloud Computing", url="https://a.com/2"),
        ]
        result = dedup.deduplicate(items)

        assert len(result) == 2

    def test_batch_internal_dedup(self, db):
        """같은 배치 내 URL 중복 제거"""
        from collectors.deduplicator import Deduplicator

        dedup = Deduplicator(db)
        items = [
            _make_raw_topic(title="Article A", url="https://same.com/1"),
            _make_raw_topic(title="Article B", url="https://same.com/1"),
        ]
        result = dedup.deduplicate(items)

        assert len(result) == 1

    def test_blog_source_prioritized(self, db):
        """중복 시 source_type='blog' 우선"""
        from collectors.deduplicator import Deduplicator

        dedup = Deduplicator(db)
        items = [
            _make_raw_topic(
                title="OpenAI GPT-5 Official Announcement",
                url="https://media.com/1",
                source_type="media",
            ),
            _make_raw_topic(
                title="OpenAI GPT-5 Official Announcement",
                url="https://blog.com/1",
                source_type="blog",
            ),
        ]
        result = dedup._deduplicate_batch(items)

        assert len(result) == 1
        assert result[0].source_type == "blog"


# ═══════════════════════════════════════════
# TopicTranslator 테스트
# ═══════════════════════════════════════════

class TestTopicTranslator:
    @pytest.mark.asyncio
    async def test_korean_items_skipped(self):
        """한국어 소스는 번역 스킵"""
        from collectors.translator import TopicTranslator

        mock_client = MagicMock()
        translator = TopicTranslator(mock_client)

        items = [
            _make_raw_topic(title="한국어 제목", language="ko"),
        ]
        result = await translator.translate_batch(items)

        assert result[0].title_ko == "한국어 제목"
        mock_client.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_english_items_translated(self):
        """영어 소스는 Claude API로 번역"""
        from collectors.translator import TopicTranslator

        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value='[{"index": 0, "title_ko": "번역 제목", "summary_ko": "번역 요약"}]')
        translator = TopicTranslator(mock_client)

        items = [
            _make_raw_topic(title="English Title", language="en"),
        ]
        result = await translator.translate_batch(items)

        assert result[0].title_ko == "번역 제목"
        assert result[0].summary_ko == "번역 요약"
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_api_error_graceful(self):
        """번역 API 실패 시 원본 유지"""
        from collectors.translator import TopicTranslator

        mock_client = MagicMock()
        mock_client.call = AsyncMock(side_effect=Exception("API Error"))
        translator = TopicTranslator(mock_client)

        items = [
            _make_raw_topic(title="English Title", language="en"),
        ]
        result = await translator.translate_batch(items)

        # title_ko는 None (번역 실패)
        assert result[0].title_ko is None


# ═══════════════════════════════════════════
# CuratorAgent 테스트
# ═══════════════════════════════════════════

class TestCuratorAgent:
    @pytest.mark.asyncio
    async def test_curate_returns_scores(self):
        """큐레이션 결과에 점수 포함"""
        from agents.curator_agent import CuratorAgent

        mock_response = '''[
          {
            "id": "t1",
            "scores": {
              "korean_interest": 8,
              "popularity": 7,
              "timeliness": 9,
              "blog_fit": 8,
              "differentiation": 7,
              "trend_relevance": 8
            },
            "reason": "중요한 뉴스",
            "recommended_type": "news_briefing",
            "recommended_category": "ai_products"
          }
        ]'''

        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value=mock_response)
        curator = CuratorAgent(mock_client)

        items = [{"id": "t1", "title": "Test", "title_ko": "테스트"}]
        results = await curator.curate(items)

        assert len(results) == 1
        assert results[0].score > 0
        assert results[0].criteria_scores["korean_interest"] == 8

    @pytest.mark.asyncio
    async def test_high_score_selected(self):
        """7점 이상 → selected=True"""
        from agents.curator_agent import CuratorAgent

        mock_response = '''[{
            "id": "t1",
            "scores": {"korean_interest": 9, "popularity": 8, "timeliness": 9,
                       "blog_fit": 8, "differentiation": 8, "trend_relevance": 8},
            "reason": "빅뉴스",
            "recommended_type": "news_briefing",
            "recommended_category": "ai_products"
        }]'''

        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value=mock_response)
        curator = CuratorAgent(mock_client)

        results = await curator.curate([{"id": "t1", "title": "Big News"}])
        assert results[0].selected is True

    @pytest.mark.asyncio
    async def test_low_score_not_selected(self):
        """7점 미만 → selected=False"""
        from agents.curator_agent import CuratorAgent

        mock_response = '''[{
            "id": "t1",
            "scores": {"korean_interest": 3, "popularity": 2, "timeliness": 4,
                       "blog_fit": 3, "differentiation": 2, "trend_relevance": 3},
            "reason": "관심 낮음",
            "recommended_type": "news_briefing",
            "recommended_category": "ai_technology"
        }]'''

        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value=mock_response)
        curator = CuratorAgent(mock_client)

        results = await curator.curate([{"id": "t1", "title": "Low Interest"}])
        assert results[0].selected is False

    @pytest.mark.asyncio
    async def test_parse_response_invalid_json(self):
        """JSON 파싱 실패 시 score=0"""
        from agents.curator_agent import CuratorAgent

        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value="This is not JSON")
        curator = CuratorAgent(mock_client)

        results = await curator.curate([{"id": "t1", "title": "Test"}])
        assert len(results) == 1
        assert results[0].score == 0.0
        assert results[0].selected is False

    def test_weighted_score_calculation(self):
        """가중 평균 점수 계산"""
        from agents.curator_agent import CuratorAgent

        mock_client = MagicMock()
        curator = CuratorAgent(mock_client)

        scores = {
            "korean_interest": 10,
            "popularity": 10,
            "timeliness": 10,
            "blog_fit": 10,
            "differentiation": 10,
            "trend_relevance": 10,
        }
        result = curator._calculate_weighted_score(scores)
        assert result == 10.0

        empty_result = curator._calculate_weighted_score({})
        assert empty_result == 0.0


# ═══════════════════════════════════════════
# Repository 테스트 (RawTopic)
# ═══════════════════════════════════════════

class TestRawTopicRepository:
    def test_save_and_retrieve(self, db, repo):
        """저장 후 조회"""
        items = [
            _make_raw_topic(title="Title 1", url="https://a.com/1"),
            _make_raw_topic(title="Title 2", url="https://a.com/2"),
        ]
        saved = repo.save_raw_topics(items)
        assert saved == 2

        collected = repo.get_raw_topics_by_status("collected")
        assert len(collected) == 2

    def test_url_unique_constraint(self, db, repo):
        """같은 URL 중복 저장 시 스킵"""
        items1 = [_make_raw_topic(url="https://dup.com/1")]
        items2 = [_make_raw_topic(title="Diff Title", url="https://dup.com/1")]

        repo.save_raw_topics(items1)
        saved = repo.save_raw_topics(items2)

        assert saved == 0  # 중복이라 0개 저장

    def test_update_curated(self, db, repo):
        """큐레이션 결과 업데이트"""
        items = [_make_raw_topic(url="https://cur.com/1")]
        repo.save_raw_topics(items)

        raw_topics = repo.get_raw_topics_by_status("collected")
        raw_id = raw_topics[0].id

        result = CurationResult(
            raw_topic_id=raw_id,
            score=8.5,
            criteria_scores={"korean_interest": 9},
            reason="중요 뉴스",
            recommended_type="news_briefing",
            recommended_category="ai_products",
            selected=True,
        )
        repo.update_raw_topic_curated(raw_id, result)

        selected = repo.get_raw_topics_by_status("selected")
        assert len(selected) == 1
        assert selected[0].curator_score == 8.5

    def test_mark_used(self, db, repo):
        """사용된 주제 상태 변경"""
        items = [_make_raw_topic(url="https://used.com/1")]
        repo.save_raw_topics(items)

        raw_topics = repo.get_raw_topics_by_status("collected")
        raw_id = raw_topics[0].id

        repo.mark_raw_topic_used(raw_id, "topic_123")

        used = repo.get_raw_topics_by_status("used")
        assert len(used) == 1
        assert used[0].used_topic_id == "topic_123"

    def test_get_recent_titles(self, db, repo):
        """최근 7일 제목 조회"""
        items = [
            _make_raw_topic(title="Recent Title", url="https://r.com/1"),
        ]
        repo.save_raw_topics(items)

        titles = repo.get_recent_raw_topic_titles(days=7)
        assert len(titles) == 1
        assert titles[0][0] == "Recent Title"
