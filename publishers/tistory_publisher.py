"""
TistoryPublisher — 티스토리 발행기
Tistory Open API를 통해 글을 자동 발행합니다.
"""

import os
from typing import Optional

import httpx
import structlog

from agents.data_models import PublishResult

logger = structlog.get_logger()

TISTORY_API_URL = "https://www.tistory.com/apis/post/write"


class TistoryPublisher:
    """티스토리 발행기

    Tistory Open API를 사용하여
    Markdown 글을 자동 발행합니다.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        blog_name: Optional[str] = None,
    ):
        self.access_token = access_token or os.getenv(
            "TISTORY_ACCESS_TOKEN", ""
        )
        self.blog_name = blog_name or os.getenv("TISTORY_BLOG_NAME", "")
        self.logger = logger.bind(module="tistory_publisher")

    async def publish(
        self,
        title: str,
        content: str,
        category_id: str = "0",
        tags: Optional[list[str]] = None,
        visibility: int = 3,  # 0: 비공개, 3: 공개
    ) -> PublishResult:
        """글 발행

        Args:
            title: 글 제목
            content: 글 본문 (Markdown)
            category_id: 카테고리 ID
            tags: 태그 목록
            visibility: 공개 설정 (0: 비공개, 3: 공개)

        Returns:
            PublishResult: 발행 결과
        """
        if not self.access_token:
            return PublishResult(
                success=False,
                platform="tistory",
                error="TISTORY_ACCESS_TOKEN이 설정되지 않았습니다",
            )

        payload = {
            "access_token": self.access_token,
            "output": "json",
            "blogName": self.blog_name,
            "title": title,
            "content": content,
            "category": category_id,
            "visibility": str(visibility),
        }

        if tags:
            payload["tag"] = ",".join(tags)

        self.logger.info("tistory.publish.start", title=title)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    TISTORY_API_URL, data=payload, timeout=30.0
                )
                data = response.json()

            tistory_resp = data.get("tistory", {})
            if tistory_resp.get("status") == "200":
                post_id = tistory_resp.get("postId", "")
                url = f"https://{self.blog_name}.tistory.com/{post_id}"
                self.logger.info(
                    "tistory.publish.success", post_id=post_id, url=url
                )
                return PublishResult(
                    success=True,
                    platform="tistory",
                    published_url=url,
                    post_id=str(post_id),
                )
            else:
                error = tistory_resp.get("error_message", "알 수 없는 에러")
                self.logger.error("tistory.publish.failed", error=error)
                return PublishResult(
                    success=False, platform="tistory", error=error
                )

        except Exception as e:
            self.logger.error(
                "tistory.publish.exception", error=str(e), exc_info=True
            )
            return PublishResult(
                success=False, platform="tistory", error=str(e)
            )
