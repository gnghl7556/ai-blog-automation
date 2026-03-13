"""
TrendCollector — 검색 트렌드 수집기
Google Trends (pytrends) + 네이버 데이터랩 (optional).
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import structlog
import yaml

from agents.data_models import TrendData

logger = structlog.get_logger()

HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class TrendCollector:
    """검색 트렌드 수집기

    Args:
        keywords_config: 키워드 설정 리스트. None이면 YAML에서 로드.
    """

    def __init__(
        self,
        keywords_config: Optional[list[dict]] = None,
    ):
        self.keywords_config = (
            keywords_config or self._load_keywords()
        )
        self.logger = logger.bind(module="trend_collector")

    def _load_keywords(self) -> list[dict]:
        """data_sources.yaml의 tracking_keywords 로드

        Returns:
            카테고리별 키워드 설정 리스트
        """
        config_path = Path("config/data_sources.yaml")
        if not config_path.exists():
            return [
                {
                    "category": "AI",
                    "keywords": ["ChatGPT", "AI", "GPT"],
                }
            ]

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        trend_sources = (
            data.get("domestic_sources", {})
            .get("trend_monitoring", {})
            .get("sources", [])
        )
        for src in trend_sources:
            if src.get("name") == "네이버 데이터랩":
                return src.get("tracking_keywords", [])

        return [
            {"category": "AI", "keywords": ["ChatGPT", "AI", "GPT"]}
        ]

    async def collect_all(self) -> list[TrendData]:
        """Google Trends + (optional) 네이버 데이터랩 수집

        Returns:
            TrendData 리스트
        """
        results: list[TrendData] = []

        try:
            google_results = await self._collect_google_trends()
            results.extend(google_results)
        except Exception as e:
            self.logger.error(
                "trend_collector.google_failed", error=str(e),
            )

        if self._has_naver_credentials():
            naver_results = await self._collect_naver_datalab()
            results.extend(naver_results)
        else:
            self.logger.info(
                "trend_collector.naver_skipped",
                reason="credentials not set",
            )

        self.logger.info(
            "trend_collector.collect_all_done",
            total=len(results),
        )
        return results

    async def _collect_google_trends(self) -> list[TrendData]:
        """pytrends로 Google Trends 수집

        키워드 5개 단위 배치 (pytrends 제한).
        동기 라이브러리이므로 asyncio.to_thread 사용.

        Returns:
            TrendData 리스트
        """
        results: list[TrendData] = []

        all_keywords: list[tuple[str, str]] = []
        for group in self.keywords_config:
            category = group.get("category", "AI")
            for kw in group.get("keywords", []):
                all_keywords.append((kw, category))

        batches: list[list[tuple[str, str]]] = []
        for i in range(0, len(all_keywords), 5):
            batches.append(all_keywords[i : i + 5])

        for batch in batches:
            try:
                batch_results = await asyncio.to_thread(
                    self._fetch_google_batch, batch,
                )
                results.extend(batch_results)
            except Exception as e:
                kw_names = [kw for kw, _ in batch]
                self.logger.error(
                    "trend_collector.google_batch_failed",
                    keywords=kw_names,
                    error=str(e),
                )

        return results

    def _fetch_google_batch(
        self, batch: list[tuple[str, str]],
    ) -> list[TrendData]:
        """pytrends 동기 호출 (to_thread에서 실행)

        Args:
            batch: (키워드, 카테고리) 튜플 리스트 (최대 5개)

        Returns:
            TrendData 리스트
        """
        from pytrends.request import TrendReq

        kw_list = [kw for kw, _ in batch]
        cat_map = {kw: cat for kw, cat in batch}

        pytrends = TrendReq(hl="ko", tz=540)
        pytrends.build_payload(kw_list, geo="KR", timeframe="now 7-d")

        df = pytrends.interest_over_time()
        if df.empty:
            return []

        results: list[TrendData] = []
        for kw in kw_list:
            if kw in df.columns:
                score = float(df[kw].iloc[-1])
                results.append(
                    TrendData(
                        keyword=kw,
                        source="google_trends",
                        score=score,
                        category=cat_map.get(kw, "AI"),
                    )
                )

        return results

    def _has_naver_credentials(self) -> bool:
        """네이버 API 키 존재 확인"""
        return bool(
            os.environ.get("NAVER_CLIENT_ID")
            and os.environ.get("NAVER_CLIENT_SECRET")
        )

    async def _collect_naver_datalab(self) -> list[TrendData]:
        """네이버 데이터랩 API 호출

        Returns:
            TrendData 리스트
        """
        client_id = os.environ["NAVER_CLIENT_ID"]
        client_secret = os.environ["NAVER_CLIENT_SECRET"]

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")

        results: list[TrendData] = []

        async with httpx.AsyncClient(
            timeout=HTTPX_TIMEOUT
        ) as client:
            for group in self.keywords_config:
                category = group.get("category", "AI")
                keywords = group.get("keywords", [])

                keyword_groups = [
                    {
                        "groupName": kw,
                        "keywords": [kw],
                    }
                    for kw in keywords[:5]
                ]

                body = {
                    "startDate": start_date,
                    "endDate": end_date,
                    "timeUnit": "date",
                    "keywordGroups": keyword_groups,
                }

                try:
                    resp = await client.post(
                        "https://openapi.naver.com/v1/datalab/search",
                        json=body,
                        headers={
                            "X-Naver-Client-Id": client_id,
                            "X-Naver-Client-Secret": client_secret,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for result in data.get("results", []):
                        kw = result.get("title", "")
                        ratios = result.get("data", [])
                        score = (
                            ratios[-1].get("ratio", 0)
                            if ratios else 0
                        )
                        results.append(
                            TrendData(
                                keyword=kw,
                                source="naver_datalab",
                                score=float(score),
                                category=category,
                            )
                        )
                except Exception as e:
                    self.logger.error(
                        "trend_collector.naver_failed",
                        category=category,
                        error=str(e),
                    )

        return results
