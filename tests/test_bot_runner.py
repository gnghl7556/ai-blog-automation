"""
BotRunner 테스트 — 콜백 처리 + 승인/반려/수정 흐름
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from database.repository import ContentRepository
from database.models import TopicStatus
from approval.bot_runner import BotRunner
from agents.data_models import (
    TopicPackage, EditResult, SEOResult, PublishResult,
)


@pytest.fixture
def mock_notifier():
    """Mock TelegramNotifier"""
    from utils.notification import TelegramNotifier
    notifier = MagicMock(spec=TelegramNotifier)
    notifier.bot_token = "test_token"
    notifier.chat_id = "test_chat"
    notifier.send_message = AsyncMock(return_value={"ok": True})
    notifier.answer_callback = AsyncMock(return_value={"ok": True})
    return notifier


@pytest.fixture
def runner(db, mock_notifier):
    """BotRunner 인스턴스"""
    return BotRunner(db_manager=db, notifier=mock_notifier)


def _seed_topic(repo, topic_id="test_topic"):
    """테스트용 주제 + 콘텐츠 2개 생성"""
    pkg = TopicPackage(
        topic_id=topic_id, title="테스트 주제",
        keywords=["AI"], category="ai_products",
        content_type="news_briefing", source="manual",
        curator_score=8.0,
    )
    repo.save_topic(pkg)

    edit = EditResult(
        content_id="e1", platform="naver",
        final_draft="본문", quality_score=8.0,
        quality_detail={}, edit_summary={}, passed=True,
    )
    seo = SEOResult(
        content_id="s1", platform="naver",
        title_final="제목", optimized_body="본문",
        seo_score=8.0, tags=["AI"],
    )
    repo.save_content(topic_id, "naver", edit, seo, "<h1>네이버</h1>")

    edit_t = EditResult(
        content_id="e2", platform="tistory",
        final_draft="본문", quality_score=8.0,
        quality_detail={}, edit_summary={}, passed=True,
    )
    seo_t = SEOResult(
        content_id="s2", platform="tistory",
        title_final="제목", optimized_body="본문",
        seo_score=8.0, tags=["AI"],
    )
    repo.save_content(topic_id, "tistory", edit_t, seo_t, "# 티스토리")
    repo.update_topic_status(topic_id, TopicStatus.REVIEW)


class TestProcessUpdate:
    """_process_update 콜백 처리 테스트"""

    @pytest.mark.asyncio
    async def test_approve_callback(self, runner, db):
        """승인 콜백 → DB 상태 approved + 자동 발행 시도"""
        repo = ContentRepository(db)
        _seed_topic(repo, "cb_approve")

        update = {
            "update_id": 1,
            "callback_query": {
                "id": "123",
                "data": "approve:cb_approve",
                "message": {"chat": {"id": "test_chat"}},
            },
        }

        with patch.object(
            runner, "_auto_publish", new=AsyncMock()
        ) as mock_pub:
            await runner._process_update(update)

        topic = repo.get_topic("cb_approve")
        assert topic.status == TopicStatus.APPROVED.value
        mock_pub.assert_awaited_once_with("cb_approve")

    @pytest.mark.asyncio
    async def test_reject_callback(self, runner, db):
        """반려 콜백 → DB 상태 rejected"""
        repo = ContentRepository(db)
        _seed_topic(repo, "cb_reject")

        update = {
            "update_id": 2,
            "callback_query": {
                "id": "456",
                "data": "reject:cb_reject",
                "message": {"chat": {"id": "test_chat"}},
            },
        }

        await runner._process_update(update)

        topic = repo.get_topic("cb_reject")
        assert topic.status == TopicStatus.REJECTED.value

    @pytest.mark.asyncio
    async def test_revise_callback(self, runner, db):
        """수정 콜백 → DB 상태 editing"""
        repo = ContentRepository(db)
        _seed_topic(repo, "cb_revise")

        update = {
            "update_id": 3,
            "callback_query": {
                "id": "789",
                "data": "revise:cb_revise",
                "message": {"chat": {"id": "test_chat"}},
            },
        }

        await runner._process_update(update)

        topic = repo.get_topic("cb_revise")
        assert topic.status == TopicStatus.EDITING.value

    @pytest.mark.asyncio
    async def test_no_callback_query_ignored(self, runner):
        """callback_query 없는 업데이트는 무시"""
        update = {"update_id": 4, "message": {"text": "hello"}}
        await runner._process_update(update)  # 에러 없이 통과


class TestAutoPublish:
    """_auto_publish 자동 발행 테스트"""

    @pytest.mark.asyncio
    async def test_auto_publish_calls_pipeline(self, runner, db):
        """자동 발행 시 Pipeline.publish() 호출"""
        repo = ContentRepository(db)
        _seed_topic(repo, "auto_pub")
        repo.update_topic_status("auto_pub", TopicStatus.APPROVED)

        mock_result = MagicMock()
        mock_result.status = "published"
        mock_result.naver_publish_result = PublishResult(
            success=True, platform="naver",
            published_url="https://naver.com/1",
        )
        mock_result.tistory_publish_result = PublishResult(
            success=True, platform="tistory",
            published_url="https://tistory.com/1",
        )

        with patch("pipeline.Pipeline") as MockPipeline, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_pipe = MockPipeline.return_value
            mock_pipe.publish = AsyncMock(return_value=mock_result)

            await runner._auto_publish("auto_pub")

            mock_pipe.publish.assert_awaited_once_with("auto_pub")

    @pytest.mark.asyncio
    async def test_auto_publish_error_sends_notification(
        self, runner, db, mock_notifier,
    ):
        """발행 실패 시 에러 알림 전송"""
        repo = ContentRepository(db)
        _seed_topic(repo, "auto_fail")

        with patch("pipeline.Pipeline") as MockPipeline, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_pipe = MockPipeline.return_value
            mock_pipe.publish = AsyncMock(
                side_effect=ValueError("테스트 에러")
            )

            await runner._auto_publish("auto_fail")

            mock_notifier.send_message.assert_called()
            call_text = mock_notifier.send_message.call_args[0][0]
            assert "발행 실패" in call_text
            assert "로그를 확인" in call_text
            # 보안: 내부 에러 메시지가 사용자에게 노출되지 않아야 함
            assert "테스트 에러" not in call_text


class TestGetUpdates:
    """_get_updates Long Polling 테스트"""

    @pytest.mark.asyncio
    async def test_get_updates_success(self, runner):
        """정상 응답 처리"""
        mock_response = {
            "ok": True,
            "result": [
                {"update_id": 100, "callback_query": {"id": "1", "data": "approve:x"}},
            ],
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(
                return_value=MagicMock(json=lambda: mock_response)
            )

            updates = await runner._get_updates()

        assert len(updates) == 1
        assert runner._offset == 101

    @pytest.mark.asyncio
    async def test_get_updates_empty(self, runner):
        """빈 응답 처리"""
        mock_response = {"ok": True, "result": []}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(
                return_value=MagicMock(json=lambda: mock_response)
            )

            updates = await runner._get_updates()

        assert updates == []
        assert runner._offset == 0


class TestApprovalLogs:
    """승인/반려 시 ApprovalLog 기록 확인"""

    @pytest.mark.asyncio
    async def test_approve_creates_logs(self, runner, db):
        """승인 시 콘텐츠별 ApprovalLog 생성"""
        repo = ContentRepository(db)
        _seed_topic(repo, "log_approve")

        with patch.object(runner, "_auto_publish", new_callable=AsyncMock):
            await runner._handle_approve("log_approve")

        # approval_logs 테이블 직접 조회
        from database.models import ApprovalLog
        with db.get_session() as session:
            logs = session.query(ApprovalLog).all()
            assert len(logs) == 2  # naver + tistory
            for log in logs:
                assert log.action == "approved"

    @pytest.mark.asyncio
    async def test_reject_creates_logs(self, runner, db):
        """반려 시 콘텐츠별 ApprovalLog 생성"""
        repo = ContentRepository(db)
        _seed_topic(repo, "log_reject")

        await runner._handle_reject("log_reject")

        from database.models import ApprovalLog
        with db.get_session() as session:
            logs = session.query(ApprovalLog).all()
            assert len(logs) == 2
            for log in logs:
                assert log.action == "rejected"
