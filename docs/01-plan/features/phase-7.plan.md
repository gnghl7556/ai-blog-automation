# Phase 7: 데이터 소스 확장

> **Feature**: phase-7
> **Status**: Plan
> **Date**: 2026-03-13
> **Priority**: Should

---

## 1. 개요

현재 RSS 7개 소스만 활성화. `web_scraper.py`, `reddit_collector.py`, `trend_collector.py`가 스텁 상태(TODO).
이번 Phase에서 나머지 8개 소스를 구현하고 통합 오케스트레이터를 만든다.

### 현재 상태
- **구현 완료**: `rss_collector.py` (7개 RSS 소스), `deduplicator.py`, `translator.py`
- **스텁**: `web_scraper.py`, `reddit_collector.py`, `trend_collector.py` (4줄 TODO)
- **미존재**: `hn_collector.py`, `collector_orchestrator.py`, `config/scrapers.yaml`

### 목표
- 데이터 소스 7개 → 15개 확장
- 소스별 실패 격리 (1개 실패해도 나머지 계속)
- 수집 결과 소스별 통계 로깅

---

## 2. 구현 범위

### 2-1. Hacker News 수집기 (신규)

**파일**: `collectors/hn_collector.py`

- Algolia API 사용 (`https://hn.algolia.com/api/v1/search`)
- AI/ML 키워드 필터링 (config/data_sources.yaml의 filtering_keywords)
- 포인트 50+ 게시글만 수집
- Rate limit 관리 불필요 (Algolia API는 관대함)
- httpx 사용 (프로젝트 기존 의존성)

**입력**: 키워드 목록, 최소 포인트
**출력**: `list[RawTopicData]`

### 2-2. Reddit 수집기 (스텁 → 구현)

**파일**: `collectors/reddit_collector.py`

- httpx 기반 Reddit JSON API 사용 (PRAW 대신 — 의존성 최소화)
  - `https://www.reddit.com/r/{subreddit}/hot.json`
  - `https://www.reddit.com/r/{subreddit}/top.json?t=day`
- 대상: r/ChatGPT, r/artificial, r/MachineLearning
- Rate limit: 분당 60회 (asyncio.sleep으로 관리)
- User-Agent 헤더 필수

**입력**: 서브레딧 목록
**출력**: `list[RawTopicData]`

### 2-3. 웹 스크래퍼 (스텁 → 구현)

**파일**: `collectors/web_scraper.py`

- httpx + BeautifulSoup 기반 (Playwright 대신 — 대상 사이트들은 SSR이므로 충분)
- 대상: Anthropic News, Google DeepMind Blog, Meta AI Blog, Product Hunt AI
- 셀렉터 설정: `config/scrapers.yaml`에 사이트별 CSS 셀렉터 정의
- 사이트 구조 변경 감지: 결과 0건이면 텔레그램 알림

**설정 파일**: `config/scrapers.yaml` (신규)
```yaml
scrapers:
  anthropic:
    url: "https://www.anthropic.com/news"
    article_selector: "a[href*='/news/']"
    title_selector: "h3"
    ...
```

**입력**: scrapers.yaml 설정
**출력**: `list[RawTopicData]`

### 2-4. 트렌드 수집기 (스텁 → 구현)

**파일**: `collectors/trend_collector.py`

- **Google Trends**: pytrends 라이브러리 (이미 requirements.txt에 포함)
  - 지역: KR
  - 키워드: data_sources.yaml의 tracking_keywords
- **네이버 데이터랩**: NAVER_CLIENT_ID/SECRET 환경변수 필요
  - 없으면 스킵 (optional)
- 수집 주기: 1회/일 (schedule.yaml에서 관리)

**입력**: 트래킹 키워드 목록
**출력**: `list[dict]` (키워드별 트렌드 점수)

### 2-5. 통합 오케스트레이터 (신규)

**파일**: `collectors/collector_orchestrator.py`

- 모든 수집기를 통합 관리
- 소스별 실패 격리: `asyncio.gather(return_exceptions=True)`
- 수집 결과 소스별 통계 로깅
- 기존 `job_collect()`를 오케스트레이터로 교체

```python
class CollectorOrchestrator:
    async def collect_all() -> list[RawTopicData]:
        # RSS + HN + Reddit + WebScraper 병렬 실행
        # 개별 실패 시 나머지 계속
        # 통계 로깅
```

### 2-6. 스케줄 업데이트

**파일**: `config/schedule.yaml` 수정, `scheduler/jobs.py` 수정

- `job_collect()`가 오케스트레이터를 호출하도록 변경
- 트렌드 수집 별도 스케줄 추가 (매일 06:00, 1회)

---

## 3. 구현 순서

```
Step 1: config/scrapers.yaml 작성 (스크래퍼 설정)
Step 2: collectors/hn_collector.py (가장 간단, API 1개)
Step 3: collectors/reddit_collector.py (JSON API, rate limit)
Step 4: collectors/web_scraper.py (BeautifulSoup, 4개 사이트)
Step 5: collectors/trend_collector.py (pytrends + optional 네이버)
Step 6: collectors/collector_orchestrator.py (통합)
Step 7: scheduler/jobs.py 수정 (오케스트레이터 연동)
Step 8: 테스트 작성
```

---

## 4. 수정/생성 파일 목록

### 신규 (4개)
- `collectors/hn_collector.py` (~120줄)
- `collectors/collector_orchestrator.py` (~150줄)
- `config/scrapers.yaml` (~60줄)
- `tests/test_collectors.py` (~200줄)

### 수정 (4개)
- `collectors/web_scraper.py` (4줄 TODO → ~150줄)
- `collectors/reddit_collector.py` (4줄 TODO → ~130줄)
- `collectors/trend_collector.py` (4줄 TODO → ~120줄)
- `scheduler/jobs.py` (오케스트레이터 연동)

### 재사용
- `agents/data_models.py` — `RawTopicData` 모델
- `collectors/deduplicator.py` — 중복 제거
- `collectors/translator.py` — 번역
- `config/data_sources.yaml` — 소스 설정

---

## 5. 의존성

### 기존 (추가 설치 불필요)
- `httpx` — HTTP 클라이언트 (HN, Reddit, 웹스크래핑)
- `beautifulsoup4` — HTML 파싱
- `pytrends` — Google Trends
- `feedparser` — RSS (기존)

### 환경변수 (optional)
- `NAVER_CLIENT_ID` — 네이버 데이터랩 API
- `NAVER_CLIENT_SECRET` — 네이버 데이터랩 API
- `REDDIT_USER_AGENT` — Reddit API User-Agent (기본값 제공)

---

## 6. 리스크 및 대응

| 리스크 | 확률 | 대응 |
|--------|------|------|
| 스크래핑 대상 사이트 구조 변경 | 중 | 결과 0건 시 텔레그램 알림, scrapers.yaml만 수정 |
| Reddit rate limit 초과 | 낮 | asyncio.sleep(1) 삽입, 분당 요청 수 제한 |
| pytrends 차단 (Google) | 중 | 실패 시 스킵, 나머지 소스로 계속 |
| 네이버 API 키 미설정 | 낮 | optional 처리, 없으면 Google Trends만 사용 |

---

## 7. Out of Scope

- X(Twitter) API (비용 문제)
- YouTube 채널 스크래핑
- arxiv 논문 수집
- Playwright 기반 렌더링 (SSR 사이트이므로 불필요)
- PRAW 라이브러리 (httpx JSON API로 대체)

---

## 8. 검증 방법

1. `python -m pytest tests/ -v` — 전체 테스트 통과
2. 개별 수집기 단독 테스트:
   - `python -c "from collectors.hn_collector import ..."`
   - `python -c "from collectors.reddit_collector import ..."`
3. 오케스트레이터 통합 테스트:
   - 1개 소스 실패 시 나머지 정상 수집 확인
4. `python cli.py collect` — 전체 수집 실행 (실제 API 호출)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-13 | Initial plan |
