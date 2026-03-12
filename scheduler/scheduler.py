"""
BlogScheduler — APScheduler 기반 블로그 자동화 스케줄러
config/schedule.yaml의 설정에 따라 작업을 등록하고 실행합니다.
"""

from pathlib import Path

import yaml
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.jobs import (
    job_collect,
    job_curate,
    job_generate,
    job_cleanup,
    job_daily_summary,
)

logger = structlog.get_logger()

# 작업 이름 → 함수 매핑
JOB_FUNCTIONS = {
    "collect": job_collect,
    "curate": job_curate,
    "generate": job_generate,
    "cleanup": job_cleanup,
}

NOTIFICATION_FUNCTIONS = {
    "daily_summary": job_daily_summary,
}


class BlogScheduler:
    """APScheduler 기반 블로그 자동화 스케줄러

    Args:
        config_path: schedule.yaml 경로
    """

    def __init__(self, config_path: str = "config/schedule.yaml"):
        self.logger = logger.bind(module="scheduler")
        self.config = self._load_config(config_path)
        self.scheduler = AsyncIOScheduler(
            timezone=self.config["scheduler"]["timezone"]
        )

    def _load_config(self, path: str) -> dict:
        """스케줄 설정 YAML 로드

        Args:
            path: YAML 파일 경로

        Returns:
            파싱된 설정 딕셔너리

        Raises:
            FileNotFoundError: 설정 파일이 없을 때
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"스케줄 설정 파일을 찾을 수 없습니다: {path}"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.logger.info(
            "scheduler.config_loaded",
            timezone=config["scheduler"]["timezone"],
            jobs=len(config.get("jobs", {})),
        )
        return config

    def setup_jobs(self) -> None:
        """설정 기반 작업 등록

        enabled=True인 작업만 등록합니다.
        CronTrigger.from_crontab()으로 cron 표현식을 파싱합니다.
        """
        # jobs 섹션 등록
        for name, job_config in self.config.get("jobs", {}).items():
            if not job_config.get("enabled", True):
                self.logger.info(
                    "scheduler.job_skipped", job=name, reason="disabled"
                )
                continue

            func = JOB_FUNCTIONS.get(name)
            if not func:
                self.logger.warning(
                    "scheduler.unknown_job", job=name
                )
                continue

            cron_expr = job_config["cron"]
            trigger = CronTrigger.from_crontab(cron_expr)

            # 작업별 추가 인자
            kwargs = {}
            if name == "generate" and "count" in job_config:
                kwargs["count"] = job_config["count"]
            elif name == "cleanup" and "retention_days" in job_config:
                kwargs["retention_days"] = job_config["retention_days"]

            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=f"job_{name}",
                name=job_config.get("description", name),
                kwargs=kwargs,
                replace_existing=True,
            )
            self.logger.info(
                "scheduler.job_registered",
                job=name,
                cron=cron_expr,
            )

        # notifications 섹션 등록
        for name, notif_config in self.config.get(
            "notifications", {}
        ).items():
            if not notif_config.get("enabled", True):
                continue

            func = NOTIFICATION_FUNCTIONS.get(name)
            if not func:
                self.logger.warning(
                    "scheduler.unknown_notification", name=name
                )
                continue

            cron_expr = notif_config["cron"]
            trigger = CronTrigger.from_crontab(cron_expr)

            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=f"notif_{name}",
                name=notif_config.get("description", name),
                replace_existing=True,
            )
            self.logger.info(
                "scheduler.notification_registered",
                name=name,
                cron=cron_expr,
            )

    def start(self) -> None:
        """스케줄러 시작

        setup_jobs()를 호출하고 AsyncIOScheduler를 시작합니다.
        """
        self.setup_jobs()
        self.scheduler.start()
        self.logger.info("scheduler.started")

    def stop(self) -> None:
        """스케줄러 정지"""
        self.scheduler.shutdown(wait=False)
        self.logger.info("scheduler.stopped")

    def get_next_runs(self) -> list[dict]:
        """다음 실행 예정 시간 조회

        Returns:
            작업별 다음 실행 정보 리스트
        """
        result = []
        for job in self.scheduler.get_jobs():
            result.append({
                "job": job.id,
                "description": job.name,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger),
            })

        result.sort(
            key=lambda x: x["next_run"] if x["next_run"] else ""
        )
        return result
