"""
Phase 5 — 스케줄 작업 함수 + Lock + Repository 확장 테스트
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scheduler.jobs import (
    job_collect,
    job_curate,
    job_generate,
    job_cleanup,
    job_daily_summary,
    get_job_lock,
    _locks,
)


# ── Lock 테스트 ──

class TestJobLock:
    """작업 Lock 테스트"""

    def setup_method(self):
        """각 테스트 전 Lock 초기화"""
        _locks.clear()

    def test_get_job_lock_creates_new(self):
        """새 Lock 생성"""
        lock = get_job_lock("test_job")
        assert isinstance(lock, asyncio.Lock)
        assert "test_job" in _locks

    def test_get_job_lock_returns_same(self):
        """동일 이름은 같은 Lock 반환"""
        lock1 = get_job_lock("test_job")
        lock2 = get_job_lock("test_job")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent(self):
        """동시 실행 시 두 번째 호출 스킵"""
        _locks.clear()
        lock = get_job_lock("collect")

        results = []

        async def slow_job():
            if lock.locked():
                results.append("skipped")
                return
            async with lock:
                await asyncio.sleep(0.1)
                results.append("done")

        await asyncio.gather(slow_job(), slow_job())
        assert "done" in results
        assert "skipped" in results

    @pytest.mark.asyncio
    async def test_lock_releases_after_complete(self):
        """작업 완료 후 Lock 해제"""
        _locks.clear()
        lock = get_job_lock("test_release")

        async with lock:
            assert lock.locked()

        assert not lock.locked()


# ── job_collect 테스트 ──

class TestJobCollect:
    """job_collect 테스트"""

    def setup_method(self):
        _locks.clear()

    @pytest.mark.asyncio
    async def test_collect_success(self):
        """정상 수집 흐름"""
        mock_items = [MagicMock() for _ in range(5)]
        mock_unique = [MagicMock() for _ in range(3)]

        with patch("scheduler.jobs._get_claude_client") as mock_client, \
             patch("scheduler.jobs._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs._get_notifier", return_value=None), \
             patch("collectors.collector_orchestrator.CollectorOrchestrator") as mock_orch, \
             patch("collectors.deduplicator.Deduplicator") as mock_dedup, \
             patch("collectors.translator.TopicTranslator") as mock_trans:

            # CollectorOrchestrator mock
            orch_inst = MagicMock()
            orch_inst.collect_all = AsyncMock(return_value=mock_items)
            mock_orch.return_value = orch_inst

            # Deduplicator mock
            dedup_inst = MagicMock()
            dedup_inst.deduplicate.return_value = mock_unique
            mock_dedup.return_value = dedup_inst

            # Translator mock
            trans_inst = MagicMock()
            trans_inst.translate_batch = AsyncMock(
                return_value=mock_unique
            )
            mock_trans.return_value = trans_inst

            # Repository mock
            mock_repo = MagicMock()
            mock_repo.save_raw_topics.return_value = 3
            mock_db.return_value = (MagicMock(), mock_repo)

            result = await job_collect()

            assert result["collected"] == 5
            assert result["unique"] == 3
            assert result["saved"] == 3

    @pytest.mark.asyncio
    async def test_collect_no_items(self):
        """수집 결과 없을 때"""
        with patch("scheduler.jobs._get_claude_client"), \
             patch("scheduler.jobs._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs._get_notifier", return_value=None), \
             patch("collectors.collector_orchestrator.CollectorOrchestrator") as mock_orch:

            orch_inst = MagicMock()
            orch_inst.collect_all = AsyncMock(return_value=[])
            mock_orch.return_value = orch_inst
            mock_db.return_value = (MagicMock(), MagicMock())

            result = await job_collect()

            assert result["collected"] == 0
            assert result["saved"] == 0

    @pytest.mark.asyncio
    async def test_collect_error_handling(self):
        """수집 중 에러 시 예외 전파 안 됨"""
        with patch("scheduler.jobs._get_claude_client"), \
             patch("scheduler.jobs._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs._get_notifier", return_value=None), \
             patch("collectors.collector_orchestrator.CollectorOrchestrator") as mock_orch:

            orch_inst = MagicMock()
            orch_inst.collect_all = AsyncMock(
                side_effect=Exception("수집 에러")
            )
            mock_orch.return_value = orch_inst
            mock_db.return_value = (MagicMock(), MagicMock())

            result = await job_collect()

            assert "error" in result
            assert "수집 에러" in result["error"]


# ── job_curate 테스트 ──

class TestJobCurate:
    """job_curate 테스트"""

    def setup_method(self):
        _locks.clear()

    @pytest.mark.asyncio
    async def test_curate_success(self):
        """정상 큐레이션 흐름"""
        mock_topic = MagicMock()
        mock_topic.id = "t1"
        mock_topic.title = "Test"
        mock_topic.title_ko = "테스트"
        mock_topic.summary_ko = "요약"
        mock_topic.summary = "summary"
        mock_topic.source = "test"
        mock_topic.published_at = None

        mock_result = MagicMock()
        mock_result.raw_topic_id = "t1"
        mock_result.selected = True

        with patch("scheduler.jobs._get_claude_client"), \
             patch("scheduler.jobs._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs._get_notifier", return_value=None), \
             patch("agents.curator_agent.CuratorAgent") as mock_curator:

            mock_repo = MagicMock()
            mock_repo.get_raw_topics_by_status.return_value = [mock_topic]
            mock_db.return_value = (MagicMock(), mock_repo)

            curator_inst = MagicMock()
            curator_inst.curate = AsyncMock(return_value=[mock_result])
            mock_curator.return_value = curator_inst

            result = await job_curate()

            assert result["total"] == 1
            assert result["selected"] == 1
            mock_repo.update_raw_topic_curated.assert_called_once()

    @pytest.mark.asyncio
    async def test_curate_no_topics(self):
        """큐레이션 대상 없을 때"""
        with patch("scheduler.jobs._get_claude_client"), \
             patch("scheduler.jobs._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs._get_notifier", return_value=None):

            mock_repo = MagicMock()
            mock_repo.get_raw_topics_by_status.return_value = []
            mock_db.return_value = (MagicMock(), mock_repo)

            result = await job_curate()

            assert result["total"] == 0
            assert result["selected"] == 0


# ── job_generate 테스트 ──

class TestJobGenerate:
    """job_generate 테스트"""

    def setup_method(self):
        _locks.clear()

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """정상 생성 흐름"""
        mock_topic = MagicMock()
        mock_topic.id = "rt1"
        mock_topic.title_ko = "테스트 주제"
        mock_topic.title = "Test Topic"
        mock_topic.curator_score = 8.5
        mock_topic.recommended_type = "news_briefing"
        mock_topic.recommended_category = "ai_products"
        mock_topic.source = "test"
        mock_topic.url = "https://test.com"

        mock_pipe_result = MagicMock()
        mock_pipe_result.topic.topic_id = "topic1"
        mock_pipe_result.status = "pending_approval"

        with patch("scheduler.jobs_generate._get_claude_client"), \
             patch("scheduler.jobs_generate._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs_generate._get_notifier", return_value=None), \
             patch("pipeline.Pipeline") as mock_pipe:

            mock_repo = MagicMock()
            mock_repo.get_raw_topics_by_status.return_value = [mock_topic]
            mock_db.return_value = (MagicMock(), mock_repo)

            pipe_inst = MagicMock()
            pipe_inst.run = AsyncMock(return_value=mock_pipe_result)
            mock_pipe.return_value = pipe_inst

            result = await job_generate(count=2)

            assert result["attempted"] == 1
            assert result["success"] == 1
            assert result["failed"] == 0
            mock_repo.mark_raw_topic_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_count(self):
        """count 인자 전달 확인"""
        topics = []
        for i in range(5):
            t = MagicMock()
            t.id = f"rt{i}"
            t.title_ko = f"주제 {i}"
            t.title = f"Topic {i}"
            t.curator_score = 8.0 - i * 0.5
            t.recommended_type = "news_briefing"
            t.recommended_category = "ai_products"
            t.source = "test"
            t.url = f"https://test.com/{i}"
            topics.append(t)

        mock_result = MagicMock()
        mock_result.topic.topic_id = "topic_x"
        mock_result.status = "pending_approval"

        with patch("scheduler.jobs_generate._get_claude_client"), \
             patch("scheduler.jobs_generate._get_db_and_repo") as mock_db, \
             patch("scheduler.jobs_generate._get_notifier", return_value=None), \
             patch("pipeline.Pipeline") as mock_pipe:

            mock_repo = MagicMock()
            mock_repo.get_raw_topics_by_status.return_value = topics
            mock_db.return_value = (MagicMock(), mock_repo)

            pipe_inst = MagicMock()
            pipe_inst.run = AsyncMock(return_value=mock_result)
            mock_pipe.return_value = pipe_inst

            result = await job_generate(count=3)

            # 5개 중 상위 3개만 시도
            assert result["attempted"] == 3
            assert result["success"] == 3


# ── job_cleanup 테스트 ──

class TestJobCleanup:
    """job_cleanup 테스트"""

    def setup_method(self):
        _locks.clear()

    @pytest.mark.asyncio
    async def test_cleanup_success(self):
        """정상 정리 흐름"""
        with patch("scheduler.jobs_generate._get_db_and_repo") as mock_db:
            mock_repo = MagicMock()
            mock_repo.cleanup_old_raw_topics.return_value = 15
            mock_db.return_value = (MagicMock(), mock_repo)

            result = await job_cleanup(retention_days=30)

            assert result["deleted"] == 15
            mock_repo.cleanup_old_raw_topics.assert_called_once_with(30)


# ── job_daily_summary 테스트 ──

class TestJobDailySummary:
    """job_daily_summary 테스트"""

    @pytest.mark.asyncio
    async def test_summary_sends_message(self):
        """텔레그램 메시지 전송 확인"""
        stats = {
            "collected": 45,
            "curated": 40,
            "selected": 8,
            "generated": 2,
            "published": 1,
            "pending": 1,
        }

        mock_notifier = MagicMock()
        mock_notifier.send_message = AsyncMock()

        with patch("scheduler.jobs_generate._get_db_and_repo") as mock_db, \
             patch(
                 "scheduler.jobs_generate._get_notifier",
                 return_value=mock_notifier,
             ):

            mock_repo = MagicMock()
            mock_repo.get_daily_stats.return_value = stats
            mock_db.return_value = (MagicMock(), mock_repo)

            await job_daily_summary()

            mock_notifier.send_message.assert_called_once()
            msg = mock_notifier.send_message.call_args[0][0]
            assert "수집: 45개" in msg
            assert "선정: 8개" in msg
            assert "발행: 1개" in msg

    @pytest.mark.asyncio
    async def test_summary_no_notifier(self):
        """notifier 없을 때 에러 없이 완료"""
        with patch("scheduler.jobs_generate._get_db_and_repo") as mock_db, \
             patch(
                 "scheduler.jobs_generate._get_notifier", return_value=None
             ):

            mock_repo = MagicMock()
            mock_repo.get_daily_stats.return_value = {
                "collected": 0, "curated": 0, "selected": 0,
                "generated": 0, "published": 0, "pending": 0,
            }
            mock_db.return_value = (MagicMock(), mock_repo)

            # 에러 없이 완료되어야 함
            await job_daily_summary()


# ── Repository 확장 메서드 테스트 ──

class TestRepositoryCleanup:
    """Repository 확장 메서드 테스트 (실제 DB)"""

    @pytest.fixture
    def db_setup(self):
        """테스트용 DB 설정"""
        from database.session import DatabaseManager
        from database.repository import ContentRepository
        from database.models import RawTopic

        db = DatabaseManager(database_url="sqlite:///:memory:")
        db.create_tables()
        repo = ContentRepository(db)
        return db, repo

    def test_cleanup_old_raw_topics(self, db_setup):
        """오래된 skipped/used 항목 삭제"""
        from database.models import RawTopic

        db, repo = db_setup
        old_date = datetime.utcnow() - timedelta(days=45)

        with db.get_session() as session:
            # 오래된 skipped (삭제 대상)
            session.add(RawTopic(
                id="old1", title="Old1", url="https://old1.com",
                source="test", status="skipped",
                collected_at=old_date,
            ))
            # 오래된 used (삭제 대상)
            session.add(RawTopic(
                id="old2", title="Old2", url="https://old2.com",
                source="test", status="used",
                collected_at=old_date,
            ))
            # 최근 skipped (보존)
            session.add(RawTopic(
                id="new1", title="New1", url="https://new1.com",
                source="test", status="skipped",
            ))

        deleted = repo.cleanup_old_raw_topics(retention_days=30)
        assert deleted == 2

        # 최근 것은 보존 확인
        remaining = repo.get_raw_topics_by_status("skipped")
        assert len(remaining) == 1
        assert remaining[0].id == "new1"

    def test_cleanup_preserves_collected(self, db_setup):
        """collected/selected 상태 보존"""
        from database.models import RawTopic

        db, repo = db_setup
        old_date = datetime.utcnow() - timedelta(days=45)

        with db.get_session() as session:
            # 오래된 collected (보존)
            session.add(RawTopic(
                id="c1", title="Collected", url="https://c1.com",
                source="test", status="collected",
                collected_at=old_date,
            ))
            # 오래된 selected (보존)
            session.add(RawTopic(
                id="s1", title="Selected", url="https://s1.com",
                source="test", status="selected",
                collected_at=old_date,
            ))

        deleted = repo.cleanup_old_raw_topics(retention_days=30)
        assert deleted == 0

    def test_get_daily_stats(self, db_setup):
        """오늘의 통계 정확성"""
        from database.models import RawTopic, Topic, TopicStatus

        db, repo = db_setup

        with db.get_session() as session:
            # 오늘의 raw_topics
            session.add(RawTopic(
                id="rt1", title="T1", url="https://t1.com",
                source="test", status="collected",
            ))
            session.add(RawTopic(
                id="rt2", title="T2", url="https://t2.com",
                source="test", status="selected",
            ))
            session.add(RawTopic(
                id="rt3", title="T3", url="https://t3.com",
                source="test", status="skipped",
            ))

            # 오늘의 topics
            session.add(Topic(
                id="tp1", title="Topic1",
                status=TopicStatus.REVIEW.value,
            ))

        stats = repo.get_daily_stats()
        assert stats["collected"] == 3  # 모든 raw_topics
        assert stats["selected"] == 1
        assert stats["curated"] == 2   # selected + skipped
        assert stats["generated"] == 1
        assert stats["pending"] == 1
