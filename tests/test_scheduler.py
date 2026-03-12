"""
Phase 5 — BlogScheduler + SchedulerRunner 테스트
"""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
import yaml

from scheduler.scheduler import BlogScheduler


# ── 테스트용 설정 파일 ──

def _create_config(tmp_path, config: dict) -> str:
    """임시 schedule.yaml 생성"""
    path = tmp_path / "schedule.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return str(path)


VALID_CONFIG = {
    "scheduler": {"timezone": "Asia/Seoul", "enabled": True},
    "jobs": {
        "collect": {
            "description": "RSS 수집",
            "cron": "0 6 * * *",
            "enabled": True,
        },
        "curate": {
            "description": "큐레이션",
            "cron": "30 6 * * *",
            "enabled": True,
        },
        "generate": {
            "description": "글 생성",
            "cron": "0 7 * * *",
            "count": 2,
            "enabled": True,
        },
        "cleanup": {
            "description": "정리",
            "cron": "0 0 * * 0",
            "retention_days": 30,
            "enabled": True,
        },
    },
    "notifications": {
        "daily_summary": {
            "description": "일일 요약",
            "cron": "0 21 * * *",
            "enabled": True,
        },
    },
}


class TestBlogScheduler:
    """BlogScheduler 단위 테스트"""

    def test_load_config(self, tmp_path):
        """schedule.yaml 로드 및 파싱 검증"""
        path = _create_config(tmp_path, VALID_CONFIG)
        sched = BlogScheduler(config_path=path)

        assert sched.config["scheduler"]["timezone"] == "Asia/Seoul"
        assert "collect" in sched.config["jobs"]
        assert sched.config["jobs"]["generate"]["count"] == 2

    def test_load_config_file_not_found(self):
        """설정 파일 없을 때 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            BlogScheduler(config_path="/nonexistent/schedule.yaml")

    def test_setup_jobs_registers_enabled(self, tmp_path):
        """enabled=True 작업만 등록 확인"""
        path = _create_config(tmp_path, VALID_CONFIG)
        sched = BlogScheduler(config_path=path)
        sched.setup_jobs()

        jobs = sched.scheduler.get_jobs()
        job_ids = [j.id for j in jobs]

        assert "job_collect" in job_ids
        assert "job_curate" in job_ids
        assert "job_generate" in job_ids
        assert "job_cleanup" in job_ids
        assert "notif_daily_summary" in job_ids
        assert len(jobs) == 5

    def test_setup_jobs_skips_disabled(self, tmp_path):
        """enabled=False 작업 스킵 확인"""
        config = {
            "scheduler": {"timezone": "Asia/Seoul", "enabled": True},
            "jobs": {
                "collect": {
                    "description": "RSS 수집",
                    "cron": "0 6 * * *",
                    "enabled": False,
                },
                "curate": {
                    "description": "큐레이션",
                    "cron": "30 6 * * *",
                    "enabled": True,
                },
            },
            "notifications": {},
        }
        path = _create_config(tmp_path, config)
        sched = BlogScheduler(config_path=path)
        sched.setup_jobs()

        jobs = sched.scheduler.get_jobs()
        job_ids = [j.id for j in jobs]

        assert "job_collect" not in job_ids
        assert "job_curate" in job_ids
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_get_next_runs(self, tmp_path):
        """다음 실행 시간 조회 형식 검증"""
        path = _create_config(tmp_path, VALID_CONFIG)
        sched = BlogScheduler(config_path=path)
        sched.setup_jobs()
        sched.scheduler.start()

        try:
            runs = sched.get_next_runs()
            assert len(runs) == 5
            for run in runs:
                assert "job" in run
                assert "description" in run
                assert "next_run" in run
                assert run["next_run"] is not None
        finally:
            sched.scheduler.shutdown(wait=False)

    def test_cron_trigger_parsing(self, tmp_path):
        """cron 표현식 파싱 검증"""
        path = _create_config(tmp_path, VALID_CONFIG)
        sched = BlogScheduler(config_path=path)
        sched.setup_jobs()

        # generate 작업의 kwargs에 count가 전달되는지 확인
        jobs = {j.id: j for j in sched.scheduler.get_jobs()}
        gen_job = jobs.get("job_generate")
        assert gen_job is not None
        assert gen_job.kwargs.get("count") == 2

        cleanup_job = jobs.get("job_cleanup")
        assert cleanup_job is not None
        assert cleanup_job.kwargs.get("retention_days") == 30

    @pytest.mark.asyncio
    async def test_start_and_stop(self, tmp_path):
        """시작/정지 동작 확인"""
        path = _create_config(tmp_path, VALID_CONFIG)
        sched = BlogScheduler(config_path=path)
        sched.start()

        assert sched.scheduler.running
        sched.stop()


class TestSchedulerRunner:
    """SchedulerRunner 통합 테스트"""

    def test_has_telegram_config_true(self, tmp_path, monkeypatch):
        """환경변수 있을 때 True"""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        path = _create_config(tmp_path, VALID_CONFIG)

        from scheduler.runner import SchedulerRunner
        runner = SchedulerRunner(config_path=path)
        assert runner._has_telegram_config() is True

    def test_has_telegram_config_false(self, tmp_path, monkeypatch):
        """환경변수 없을 때 False"""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        path = _create_config(tmp_path, VALID_CONFIG)

        from scheduler.runner import SchedulerRunner
        runner = SchedulerRunner(config_path=path)
        assert runner._has_telegram_config() is False

    def test_has_telegram_config_partial(self, tmp_path, monkeypatch):
        """토큰만 있고 chat_id 없으면 False"""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        path = _create_config(tmp_path, VALID_CONFIG)

        from scheduler.runner import SchedulerRunner
        runner = SchedulerRunner(config_path=path)
        assert runner._has_telegram_config() is False
