"""
WebScraper — httpx + BeautifulSoup 기반 웹 스크래핑 수집기
사이트별 CSS 셀렉터는 config/scrapers.yaml에서 로드합니다.
SSR 사이트 대상이므로 Playwright 불필요.
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
import structlog
import yaml
from bs4 import BeautifulSoup

from agents.data_models import RawTopicData

logger = structlog.get_logger()

HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

DEFAULT_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": (
        "Mozilla/5.0 (compatible; ai-blog-bot/1.0; "
        "+https://github.com/ai-blog-automation)"
    ),
}


class WebScraper:
    """웹 스크래핑 수집기

    Args:
        config_path: scrapers.yaml 경로
        sites: 사이트 설정 리스트 (테스트용 직접 주입)
    """

    def __init__(
        self,
        config_path: str = "config/scrapers.yaml",
        sites: Optional[list[dict]] = None,
    ):
        self.logger = logger.bind(module="web_scraper")
        self.sites = sites or self._load_config(config_path)

    def _load_config(self, path: str) -> list[dict]:
        """scrapers.yaml 로드

        Args:
            path: YAML 파일 경로

        Returns:
            사이트 설정 리스트
        """
        config_path = Path(path)
        if not config_path.exists():
            self.logger.warning(
                "web_scraper.config_not_found", path=path,
            )
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        scrapers = data.get("scrapers", {})
        return [
            {**config, "key": key}
            for key, config in scrapers.items()
        ]

    async def collect_all(self) -> list[RawTopicData]:
        """모든 사이트 수집

        사이트별 실패 격리. 결과 0건 시 경고 로그.

        Returns:
            수집된 RawTopicData 리스트
        """
        all_items: list[RawTopicData] = []

        async with httpx.AsyncClient(
            timeout=HTTPX_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            for site in self.sites:
                try:
                    items = await self._scrape_site(client, site)
                    if not items:
                        self.logger.warning(
                            "web_scraper.zero_results",
                            site=site.get("name"),
                            url=site.get("url"),
                        )
                    all_items.extend(items)
                    self.logger.info(
                        "web_scraper.site_done",
                        site=site.get("name"),
                        count=len(items),
                    )
                except Exception as e:
                    self.logger.error(
                        "web_scraper.site_failed",
                        site=site.get("name"),
                        error=str(e),
                    )

        self.logger.info(
            "web_scraper.collect_all_done",
            total=len(all_items),
        )
        return all_items

    async def _scrape_site(
        self, client: httpx.AsyncClient, site: dict,
    ) -> list[RawTopicData]:
        """단일 사이트 스크래핑

        Args:
            client: httpx 클라이언트
            site: 사이트 설정 딕셔너리

        Returns:
            RawTopicData 리스트
        """
        resp = await client.get(site["url"])
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select(site["article_selector"])

        max_items = site.get("max_items", 20)
        items: list[RawTopicData] = []

        for article in articles[:max_items]:
            item = self._element_to_raw_topic(article, site)
            if item:
                items.append(item)

        return items

    def _element_to_raw_topic(
        self, element, site: dict,
    ) -> Optional[RawTopicData]:
        """BeautifulSoup 엘리먼트 → RawTopicData 변환

        Args:
            element: BeautifulSoup 엘리먼트
            site: 사이트 설정

        Returns:
            RawTopicData 또는 None
        """
        title_el = element.select_one(site["title_selector"])
        if not title_el:
            title_text = element.get_text(strip=True)
        else:
            title_text = title_el.get_text(strip=True)

        if not title_text:
            return None

        link_attr = site.get("link_attr", "href")
        href = element.get(link_attr, "")
        if not href:
            link_el = element.find("a")
            href = link_el.get("href", "") if link_el else ""

        if not href:
            return None

        base_url = site.get("base_url", "")
        url = urljoin(base_url, href) if base_url else href

        return RawTopicData(
            title=title_text,
            url=url,
            source=site.get("name", "Unknown"),
            source_type=site.get("source_type", "blog"),
            summary="",
            language=site.get("language", "en"),
        )
