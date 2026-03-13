# Phase 7: 데이터 소스 확장 — 설계 문서

> **Feature**: phase-7
> **Status**: Design
> **Date**: 2026-03-13
> **Plan Reference**: `docs/01-plan/features/phase-7.plan.md`

---

## 1. 아키텍처 개요

```
config/data_sources.yaml          config/scrapers.yaml (신규)
        │                                  │
        ▼                                  ▼
┌──────────────────────────────────────────────────────────┐
│              CollectorOrchestrator (신규)                  │
│                                                          │
│  asyncio.gather(return_exceptions=True)                  │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐ │
│  │ RSS       │ │ HN        │ │ Reddit    │ │ Web      │ │
│  │ Collector │ │ Collector │ │ Collector │ │ Scraper  │ │
│  │ (기존)    │ │ (신규)    │ │ (구현)    │ │ (구현)   │ │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └────┬─────┘ │
│        └──────────┬───┴──────────┬──┘            │       │
│                   ▼              ▼                ▼       │
│            list[RawTopicData] (통합)                      │
└──────────────────────┬───────────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │     Deduplicator (기존)    │
         │     Translator (기존)      │
         │     DB 저장 (기존)         │
         └───────────────────────────┘

별도 스케줄:
┌───────────────────────┐
│  TrendCollector (구현) │  ← 매일 06:00, 1회/일
│  Google Trends         │
│  Naver DataLab (opt)   │
└───────────┬───────────┘
            ▼
      트렌드 데이터 → 큐레이션 참고용
```

### 기존 흐름 변경

```
Before: job_collect() → RSSCollector.collect_all() → Dedup → Translate → DB
After:  job_collect() → CollectorOrchestrator.collect_all() → Dedup → Translate → DB
```

- `job_collect()` 내부에서 `RSSCollector()` 대신 `CollectorOrchestrator()`를 호출
- 나머지 흐름(중복 제거, 번역, DB 저장)은 기존 그대로 유지

---

## 2. 데이터 모델

### 2.1 기존 모델 재사용

`agents/data_models.py`의 `RawTopicData`를 모든 수집기가 공통 출력으로 사용:

```python
class RawTopicData(BaseModel):
    title: str
    url: str
    source: str
    source_type: str = "media"       # blog, media, community
    summary: str = ""
    language: str = "en"
    published_at: Optional[datetime] = None
    title_ko: Optional[str] = None
    summary_ko: Optional[str] = None
```

### 2.2 트렌드 데이터 (신규)

트렌드 수집기는 `RawTopicData`가 아닌 별도 형식 반환:

```python
class TrendData(BaseModel):
    """트렌드 수집 결과"""
    keyword: str
    source: str          # "google_trends" | "naver_datalab"
    score: float         # 0~100 상대 점수
    category: str        # data_sources.yaml의 카테고리
    collected_at: datetime
```

> `TrendData`는 `agents/data_models.py`에 추가. 큐레이션 에이전트가 참고 데이터로 사용.

---

## 3. 클래스 설계

### 3.1 HNCollector — `collectors/hn_collector.py` (~120줄)

```python
class HNCollector:
    """Hacker News Algolia API 기반 수집기

    Args:
        min_points: 최소 포인트 (기본 50)
        keywords: 필터링 키워드 (data_sources.yaml에서 로드)
    """

    API_URL = "https://hn.algolia.com/api/v1/search"

    def __init__(
        self,
        min_points: int = 50,
        keywords: list[str] | None = None,
    ):
        self.min_points = min_points
        self.keywords = keywords or self._load_keywords()
        self.logger = structlog.get_logger().bind(module="hn_collector")

    def _load_keywords(self) -> list[str]:
        """data_sources.yaml의 filtering_keywords 로드"""
        ...

    async def collect_all(self) -> list[RawTopicData]:
        """키워드별 검색 → 포인트 필터 → RawTopicData 변환"""
        ...

    async def _search(self, query: str) -> list[dict]:
        """Algolia API 호출 (httpx)

        GET /api/v1/search?tags=story&query={query}&numericFilters=points>{min_points}
        """
        ...

    def _hit_to_raw_topic(self, hit: dict) -> RawTopicData:
        """API 응답 → RawTopicData 변환

        매핑:
        - title = hit["title"]
        - url = hit["url"] or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        - source = "Hacker News"
        - source_type = "community"
        - summary = hit.get("story_text", "")[:200]
        - published_at = datetime.fromtimestamp(hit["created_at_i"])
        """
        ...
```

**Algolia API 파라미터:**
| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `tags` | `story` | 스토리만 (댓글 제외) |
| `query` | 키워드 | AI, GPT 등 |
| `numericFilters` | `points>50` | 포인트 50+ |
| `hitsPerPage` | `30` | 키워드당 최대 30개 |

### 3.2 RedditCollector — `collectors/reddit_collector.py` (~130줄)

```python
class RedditCollector:
    """Reddit JSON API 기반 수집기

    httpx로 Reddit 공개 JSON API 호출.
    PRAW 미사용 (의존성 최소화).

    Args:
        subreddits: 대상 서브레딧 (기본: data_sources.yaml에서 로드)
        user_agent: HTTP User-Agent
    """

    BASE_URL = "https://www.reddit.com/r"
    DEFAULT_SUBREDDITS = ["ChatGPT", "artificial", "MachineLearning"]

    def __init__(
        self,
        subreddits: list[str] | None = None,
        user_agent: str | None = None,
    ):
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS
        self.user_agent = (
            user_agent
            or os.environ.get("REDDIT_USER_AGENT", "ai-blog-bot/1.0")
        )
        self.logger = structlog.get_logger().bind(module="reddit_collector")

    async def collect_all(self) -> list[RawTopicData]:
        """전체 서브레딧 수집 (hot + top/day)

        서브레딧 간 1초 대기 (rate limit 방지)
        """
        ...

    async def _fetch_listing(
        self, subreddit: str, sort: str, params: dict | None = None,
    ) -> list[dict]:
        """Reddit JSON API 호출

        GET /r/{subreddit}/{sort}.json?limit=25
        Headers: User-Agent 필수
        """
        ...

    def _post_to_raw_topic(
        self, post: dict, subreddit: str,
    ) -> RawTopicData:
        """Reddit 포스트 → RawTopicData 변환

        매핑:
        - title = post["data"]["title"]
        - url = post["data"]["url"]
        - source = f"Reddit - r/{subreddit}"
        - source_type = "community"
        - summary = post["data"]["selftext"][:200]
        - published_at = datetime.fromtimestamp(post["data"]["created_utc"])
        """
        ...
```

**Rate Limit 전략:**
- 서브레딧 간 `asyncio.sleep(1.0)` — 분당 60회 미만 보장
- hot + top/day 각각 `limit=25` → 서브레딧당 50개, 총 150개 최대

### 3.3 WebScraper — `collectors/web_scraper.py` (~150줄)

```python
class WebScraper:
    """웹 스크래핑 수집기

    httpx + BeautifulSoup 기반.
    사이트별 CSS 셀렉터는 config/scrapers.yaml에서 로드.

    Args:
        config_path: scrapers.yaml 경로
    """

    def __init__(
        self, config_path: str = "config/scrapers.yaml",
    ):
        self.sites = self._load_config(config_path)
        self.logger = structlog.get_logger().bind(module="web_scraper")

    def _load_config(self, path: str) -> list[dict]:
        """scrapers.yaml 로드 → 사이트 설정 리스트"""
        ...

    async def collect_all(self) -> list[RawTopicData]:
        """모든 사이트 수집

        사이트별 실패 격리: try/except per site
        결과 0건 시 경고 로그 (구조 변경 감지)
        """
        ...

    async def _scrape_site(self, site: dict) -> list[RawTopicData]:
        """단일 사이트 스크래핑

        1. httpx.get(url)
        2. BeautifulSoup(html, "html.parser")
        3. soup.select(article_selector)로 기사 추출
        4. 각 기사에서 title_selector, link_selector로 데이터 추출
        """
        ...

    def _element_to_raw_topic(
        self, element, site: dict,
    ) -> RawTopicData | None:
        """BeautifulSoup 엘리먼트 → RawTopicData

        매핑:
        - title = element.select_one(title_selector).text.strip()
        - url = base_url + href (상대 경로 처리)
        - source = site["name"]
        - source_type = "blog"
        """
        ...
```

### 3.4 TrendCollector — `collectors/trend_collector.py` (~120줄)

```python
class TrendCollector:
    """검색 트렌드 수집기

    Google Trends (pytrends) + 네이버 데이터랩 (optional).

    Args:
        keywords_config: 키워드 설정 (data_sources.yaml에서 로드)
    """

    def __init__(self, keywords_config: list[dict] | None = None):
        self.keywords_config = keywords_config or self._load_keywords()
        self.logger = structlog.get_logger().bind(module="trend_collector")

    def _load_keywords(self) -> list[dict]:
        """data_sources.yaml의 tracking_keywords 로드"""
        ...

    async def collect_all(self) -> list[TrendData]:
        """Google Trends + (optional) 네이버 데이터랩 수집"""
        results: list[TrendData] = []
        results.extend(await self._collect_google_trends())

        if self._has_naver_credentials():
            results.extend(await self._collect_naver_datalab())

        return results

    async def _collect_google_trends(self) -> list[TrendData]:
        """pytrends로 Google Trends 수집

        - 지역: KR
        - 키워드 5개씩 배치 (pytrends 제한)
        - interest_over_time() → 최신 값을 score로 변환
        """
        ...

    def _has_naver_credentials(self) -> bool:
        """NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 존재 확인"""
        ...

    async def _collect_naver_datalab(self) -> list[TrendData]:
        """네이버 데이터랩 API 호출

        POST https://openapi.naver.com/v1/datalab/search
        Headers: X-Naver-Client-Id, X-Naver-Client-Secret
        Body: startDate, endDate, timeUnit, keywordGroups
        """
        ...
```

**pytrends 주의사항:**
- 키워드 5개 단위 배치 필수 (API 제한)
- `await asyncio.to_thread(pytrends_func)` — pytrends는 동기 라이브러리
- Google 차단 시 예외 처리 후 빈 리스트 반환

### 3.5 CollectorOrchestrator — `collectors/collector_orchestrator.py` (~150줄)

```python
class CollectorOrchestrator:
    """수집기 통합 오케스트레이터

    모든 수집기를 병렬 실행하고 결과를 통합합니다.
    개별 수집기 실패 시 나머지는 계속 진행합니다.
    """

    def __init__(self):
        self.logger = structlog.get_logger().bind(
            module="collector_orchestrator"
        )

    async def collect_all(self) -> list[RawTopicData]:
        """전체 수집 실행

        Returns:
            모든 수집기 결과 통합 리스트

        흐름:
        1. RSS, HN, Reddit, WebScraper 인스턴스 생성
        2. asyncio.gather(return_exceptions=True)로 병렬 실행
        3. 성공 결과만 통합
        4. 소스별 통계 로깅
        """
        collectors = {
            "rss": RSSCollector(),
            "hn": HNCollector(),
            "reddit": RedditCollector(),
            "web": WebScraper(),
        }

        tasks = {
            name: collector.collect_all()
            for name, collector in collectors.items()
        }

        results = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        all_items: list[RawTopicData] = []
        stats: dict[str, int | str] = {}

        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                self.logger.error(
                    "orchestrator.collector_failed",
                    collector=name,
                    error=str(result),
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
            return await collector.collect_all()
        except Exception as e:
            self.logger.error(
                "orchestrator.trend_failed", error=str(e)
            )
            return []
```

---

## 4. 설정 파일

### 4.1 `config/scrapers.yaml` (신규)

```yaml
# 웹 스크래핑 대상 사이트 설정
# 사이트 구조 변경 시 여기만 수정

scrapers:
  anthropic:
    name: "Anthropic News"
    url: "https://www.anthropic.com/news"
    article_selector: "a[href*='/news/']"
    title_selector: "h3"
    link_attr: "href"
    base_url: "https://www.anthropic.com"
    language: "en"
    source_type: "blog"
    max_items: 20

  deepmind:
    name: "Google DeepMind Blog"
    url: "https://deepmind.google/discover/blog/"
    article_selector: "a[href*='/discover/blog/']"
    title_selector: "h3"
    link_attr: "href"
    base_url: "https://deepmind.google"
    language: "en"
    source_type: "blog"
    max_items: 20

  meta_ai:
    name: "Meta AI Blog"
    url: "https://ai.meta.com/blog/"
    article_selector: "a[href*='/blog/']"
    title_selector: "h2, h3"
    link_attr: "href"
    base_url: "https://ai.meta.com"
    language: "en"
    source_type: "blog"
    max_items: 20

  product_hunt:
    name: "Product Hunt - AI"
    url: "https://www.producthunt.com/topics/artificial-intelligence"
    article_selector: "[data-test='post-item']"
    title_selector: "h3"
    link_attr: "href"
    base_url: "https://www.producthunt.com"
    language: "en"
    source_type: "community"
    max_items: 10
```

### 4.2 `config/schedule.yaml` 수정

```yaml
# 기존 jobs에 추가:
jobs:
  collect_trends:
    description: "검색 트렌드 수집"
    cron: "0 6 * * *"       # 매일 06:00
    enabled: true
```

---

## 5. 스케줄러 연동

### 5.1 `scheduler/jobs.py` 수정 사항

```python
# 기존 job_collect() 수정:
async def job_collect() -> dict:
    # Before: from collectors.rss_collector import RSSCollector
    # After:
    from collectors.collector_orchestrator import CollectorOrchestrator

    orchestrator = CollectorOrchestrator()
    raw_items = await orchestrator.collect_all()
    # 이후 dedup → translate → DB 저장은 기존과 동일

# 신규 job_collect_trends() 추가:
async def job_collect_trends() -> dict:
    """트렌드 수집 작업 (매일 1회)"""
    from collectors.collector_orchestrator import CollectorOrchestrator

    orchestrator = CollectorOrchestrator()
    trends = await orchestrator.collect_trends()
    # TODO: 트렌드 DB 저장 (Phase 8에서 큐레이션 연동)
    return {"trends_collected": len(trends)}
```

### 5.2 `scheduler/scheduler.py` 수정 사항

- `setup_jobs()`에서 `collect_trends` job 등록 추가

---

## 6. 에러 처리 전략

### 6.1 실패 격리

```
CollectorOrchestrator
├── RSS: ✅ 성공 (30개)
├── HN:  ❌ 실패 (Timeout) → 로그만 남기고 계속
├── Reddit: ✅ 성공 (45개)
└── Web: ✅ 성공 (12개)
→ 총 87개 반환 (HN 제외하고 정상 진행)
```

### 6.2 경고 알림 조건

| 조건 | 동작 |
|------|------|
| WebScraper 결과 0건 | `logger.warning()` — 사이트 구조 변경 의심 |
| Reddit rate limit 429 | `asyncio.sleep(60)` 후 재시도 1회 |
| pytrends 차단 (429/500) | 스킵, 빈 리스트 반환 |
| Naver API 키 미설정 | `logger.info()`, Google Trends만 수집 |

### 6.3 httpx 공통 설정

```python
# 모든 수집기가 사용할 httpx 기본 설정
HTTPX_DEFAULTS = {
    "timeout": httpx.Timeout(30.0, connect=10.0),
    "follow_redirects": True,
    "headers": {"Accept-Language": "en-US,en;q=0.9"},
}
```

---

## 7. 구현 순서 및 파일 목록

### 구현 순서

```
Step 1: agents/data_models.py — TrendData 모델 추가 (~10줄)
Step 2: config/scrapers.yaml — 스크래핑 설정 (신규, ~60줄)
Step 3: collectors/hn_collector.py — HN 수집기 (신규, ~120줄)
Step 4: collectors/reddit_collector.py — Reddit 수집기 (스텁→구현, ~130줄)
Step 5: collectors/web_scraper.py — 웹 스크래퍼 (스텁→구현, ~150줄)
Step 6: collectors/trend_collector.py — 트렌드 수집기 (스텁→구현, ~120줄)
Step 7: collectors/collector_orchestrator.py — 오케스트레이터 (신규, ~150줄)
Step 8: scheduler/jobs.py — 오케스트레이터 연동 + job_collect_trends
Step 9: config/schedule.yaml — collect_trends 스케줄 추가
Step 10: tests/test_collectors.py — 전체 테스트 (~200줄)
```

### 신규 파일 (4개)

| 파일 | 줄 수 | 설명 |
|------|-------|------|
| `collectors/hn_collector.py` | ~120 | HN Algolia API 수집기 |
| `collectors/collector_orchestrator.py` | ~150 | 통합 오케스트레이터 |
| `config/scrapers.yaml` | ~60 | 웹 스크래핑 설정 |
| `tests/test_collectors.py` | ~200 | 수집기 테스트 |

### 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|----------|
| `agents/data_models.py` | `TrendData` 모델 추가 |
| `collectors/reddit_collector.py` | 스텁 → 구현 (~130줄) |
| `collectors/web_scraper.py` | 스텁 → 구현 (~150줄) |
| `collectors/trend_collector.py` | 스텁 → 구현 (~120줄) |
| `scheduler/jobs.py` | `job_collect()` 오케스트레이터 연동, `job_collect_trends()` 추가 |

---

## 8. 테스트 설계

### 8.1 `tests/test_collectors.py`

```python
class TestHNCollector:
    """HN 수집기 테스트 (httpx mock)"""
    async def test_collect_all_success(self): ...
    async def test_collect_all_empty(self): ...
    async def test_min_points_filter(self): ...
    async def test_api_error_handling(self): ...

class TestRedditCollector:
    """Reddit 수집기 테스트"""
    async def test_collect_all_success(self): ...
    async def test_rate_limit_handling(self): ...
    async def test_invalid_subreddit(self): ...
    async def test_user_agent_header(self): ...

class TestWebScraper:
    """웹 스크래퍼 테스트"""
    async def test_scrape_site_success(self): ...
    async def test_empty_results_warning(self): ...
    async def test_relative_url_resolution(self): ...
    async def test_missing_config(self): ...

class TestTrendCollector:
    """트렌드 수집기 테스트"""
    async def test_google_trends_success(self): ...
    async def test_naver_optional(self): ...
    async def test_pytrends_blocked(self): ...

class TestCollectorOrchestrator:
    """오케스트레이터 테스트"""
    async def test_all_success(self): ...
    async def test_partial_failure(self): ...
    async def test_all_failure(self): ...
    async def test_stats_logging(self): ...
```

### 8.2 테스트 전략

- **모든 HTTP 호출 mock**: `httpx.AsyncClient`를 `unittest.mock.AsyncMock`으로 대체
- **pytrends mock**: `asyncio.to_thread` 내부 함수를 mock
- **scrapers.yaml**: 테스트용 임시 YAML 생성 (`tmp_path`)
- **오케스트레이터**: 개별 수집기를 mock하여 실패 격리 검증

---

## 9. 의존성

### 기존 (추가 설치 불필요)

- `httpx` — HN, Reddit, WebScraping, Naver API
- `beautifulsoup4` — HTML 파싱
- `pytrends` — Google Trends
- `feedparser` — RSS (기존)
- `structlog` — 구조화 로깅

### 환경변수 (optional)

| 변수 | 필수 | 기본값 | 용도 |
|------|------|--------|------|
| `NAVER_CLIENT_ID` | No | — | 네이버 데이터랩 API |
| `NAVER_CLIENT_SECRET` | No | — | 네이버 데이터랩 API |
| `REDDIT_USER_AGENT` | No | `ai-blog-bot/1.0` | Reddit API |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-13 | Initial design |
