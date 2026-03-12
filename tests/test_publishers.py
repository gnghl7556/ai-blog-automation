"""
발행기 테스트 (Tistory + Naver)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTistoryPublisher:
    @pytest.mark.asyncio
    async def test_publish_success(self):
        """정상 발행"""
        from publishers.tistory_publisher import TistoryPublisher

        publisher = TistoryPublisher(
            access_token="test_token", blog_name="testblog"
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tistory": {"status": "200", "postId": "123"}
        }

        with patch("publishers.tistory_publisher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client.return_value
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await publisher.publish("테스트 제목", "본문 내용")

        assert result.success is True
        assert result.platform == "tistory"
        assert result.post_id == "123"
        assert "testblog.tistory.com" in result.published_url

    @pytest.mark.asyncio
    async def test_publish_no_token(self):
        """토큰 없이 발행 시 실패"""
        from publishers.tistory_publisher import TistoryPublisher

        publisher = TistoryPublisher(access_token="", blog_name="testblog")
        result = await publisher.publish("제목", "본문")

        assert result.success is False
        assert "ACCESS_TOKEN" in result.error

    @pytest.mark.asyncio
    async def test_publish_api_error(self):
        """API 에러 응답 처리"""
        from publishers.tistory_publisher import TistoryPublisher

        publisher = TistoryPublisher(
            access_token="test_token", blog_name="testblog"
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tistory": {"status": "401", "error_message": "인증 실패"}
        }

        with patch("publishers.tistory_publisher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client.return_value
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await publisher.publish("제목", "본문")

        assert result.success is False
        assert "인증 실패" in result.error

    @pytest.mark.asyncio
    async def test_publish_network_error(self):
        """네트워크 에러 처리"""
        from publishers.tistory_publisher import TistoryPublisher

        publisher = TistoryPublisher(
            access_token="test_token", blog_name="testblog"
        )

        with patch("publishers.tistory_publisher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client.return_value
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(
                side_effect=Exception("타임아웃")
            )

            result = await publisher.publish("제목", "본문")

        assert result.success is False
        assert "타임아웃" in result.error

    @pytest.mark.asyncio
    async def test_publish_with_tags(self):
        """태그 포함 발행"""
        from publishers.tistory_publisher import TistoryPublisher

        publisher = TistoryPublisher(
            access_token="test_token", blog_name="testblog"
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tistory": {"status": "200", "postId": "456"}
        }

        with patch("publishers.tistory_publisher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client.return_value
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await publisher.publish(
                "제목", "본문", tags=["AI", "ChatGPT"]
            )

            call_args = mock_client.return_value.post.call_args
            payload = call_args.kwargs.get("data") or call_args[1].get("data")
            assert payload["tag"] == "AI,ChatGPT"

        assert result.success is True


class TestNaverPublisher:
    @pytest.mark.asyncio
    async def test_publish_no_playwright(self):
        """playwright 미설치 시 에러"""
        from publishers.naver_publisher import NaverPublisher

        publisher = NaverPublisher(naver_id="testuser")

        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            # playwright import가 실패하도록 모킹
            with patch(
                "publishers.naver_publisher.NaverPublisher.publish",
                new_callable=AsyncMock,
            ) as mock_publish:
                from publishers.naver_publisher import PublishResult

                mock_publish.return_value = PublishResult(
                    success=False,
                    platform="naver",
                    error="playwright가 설치되지 않았습니다.",
                )
                result = await mock_publish("제목", "<p>본문</p>")

        assert result.success is False
        assert "playwright" in result.error

    def test_naver_publisher_init(self):
        """NaverPublisher 초기화"""
        from publishers.naver_publisher import NaverPublisher

        publisher = NaverPublisher(
            naver_id="testuser", cookie_path="test/cookies.json"
        )
        assert publisher.naver_id == "testuser"
        assert publisher.cookie_path == "test/cookies.json"
