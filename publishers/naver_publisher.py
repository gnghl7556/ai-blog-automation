"""
NaverPublisher — 네이버 블로그 발행기
Playwright를 사용하여 네이버 블로그에 자동 발행합니다.
네이버 블로그 API가 없으므로 브라우저 자동화를 사용합니다.
"""

import os
from typing import Optional

import structlog

from agents.data_models import PublishResult

logger = structlog.get_logger()


class NaverPublisher:
    """네이버 블로그 발행기

    Playwright를 사용하여 네이버 블로그 에디터에
    HTML 글을 자동 입력하고 발행합니다.

    NOTE: 네이버 블로그는 공식 발행 API가 없어
    브라우저 자동화를 사용합니다.
    쿠키 기반 로그인 유지가 필요합니다.
    """

    def __init__(
        self,
        naver_id: Optional[str] = None,
        cookie_path: Optional[str] = None,
    ):
        self.naver_id = naver_id or os.getenv("NAVER_BLOG_ID", "")
        self.cookie_path = cookie_path or "data/naver_cookies.json"
        self.logger = logger.bind(module="naver_publisher")

    async def publish(
        self,
        title: str,
        content_html: str,
        category: str = "",
        tags: Optional[list[str]] = None,
    ) -> PublishResult:
        """네이버 블로그에 글 발행

        Args:
            title: 글 제목
            content_html: HTML 본문
            category: 카테고리명
            tags: 태그 목록

        Returns:
            PublishResult: 발행 결과
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return PublishResult(
                success=False,
                platform="naver",
                error="playwright가 설치되지 않았습니다. "
                      "'pip install playwright && playwright install chromium'",
            )

        self.logger.info("naver.publish.start", title=title)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await self._load_context(browser)
                page = await context.new_page()

                # 1. 블로그 글쓰기 페이지 이동
                write_url = f"https://blog.naver.com/{self.naver_id}/postwrite"
                await page.goto(write_url, wait_until="networkidle")

                # 2. 로그인 확인
                if "login" in page.url.lower():
                    await browser.close()
                    return PublishResult(
                        success=False,
                        platform="naver",
                        error="네이버 로그인이 필요합니다. 쿠키를 갱신하세요.",
                    )

                # 3. 스마트에디터에 콘텐츠 입력
                # iframe 내부의 에디터에 접근
                editor_frame = page.frame(name="mainFrame")
                if not editor_frame:
                    # 프레임이 없으면 직접 접근 시도
                    editor_frame = page

                # 제목 입력
                title_input = editor_frame.locator(
                    'input[placeholder*="제목"], .se-title-input'
                )
                await title_input.fill(title)

                # HTML 모드로 전환하여 본문 입력
                await self._input_html_content(editor_frame, content_html)

                # 태그 입력
                if tags:
                    await self._input_tags(editor_frame, tags)

                # 4. 발행 버튼 클릭
                publish_btn = editor_frame.locator(
                    'button:has-text("발행"), .publish_btn'
                )
                await publish_btn.click()
                await page.wait_for_timeout(3000)

                # 5. 발행 확인
                current_url = page.url
                post_id = current_url.split("/")[-1] if "/" in current_url else ""

                await browser.close()

                published_url = (
                    f"https://blog.naver.com/{self.naver_id}/{post_id}"
                )
                self.logger.info(
                    "naver.publish.success",
                    post_id=post_id,
                    url=published_url,
                )
                return PublishResult(
                    success=True,
                    platform="naver",
                    published_url=published_url,
                    post_id=post_id,
                )

        except Exception as e:
            self.logger.error(
                "naver.publish.exception", error=str(e), exc_info=True
            )
            return PublishResult(
                success=False, platform="naver", error=str(e)
            )

    async def _load_context(self, browser):
        """저장된 쿠키로 브라우저 컨텍스트 생성"""
        import json
        from pathlib import Path

        cookie_file = Path(self.cookie_path)
        if cookie_file.exists():
            context = await browser.new_context(
                storage_state=str(cookie_file)
            )
        else:
            context = await browser.new_context()
            self.logger.warning("naver.no_cookies", path=self.cookie_path)
        return context

    async def _input_html_content(self, frame, html: str) -> None:
        """에디터에 HTML 본문 입력"""
        # 에디터 본문 영역에 HTML 삽입
        editor = frame.locator(
            '.se-component-content, [contenteditable="true"]'
        )
        await editor.click()
        # JavaScript로 HTML 직접 삽입
        await frame.evaluate(
            """(html) => {
                const editor = document.querySelector(
                    '[contenteditable="true"]'
                );
                if (editor) editor.innerHTML = html;
            }""",
            html,
        )

    async def _input_tags(self, frame, tags: list[str]) -> None:
        """태그 입력"""
        tag_input = frame.locator('input[placeholder*="태그"], .tag_input')
        for tag in tags[:10]:  # 네이버 태그 최대 10개
            await tag_input.fill(tag)
            await tag_input.press("Enter")
