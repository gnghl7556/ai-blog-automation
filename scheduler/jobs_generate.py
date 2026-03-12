"""
스케줄 작업 정의 — 글 생성, 정리, 일일 요약
scheduler/jobs.py에서 분리된 작업 함수입니다.
"""

from datetime import datetime

import structlog

from scheduler.jobs import get_job_lock, _get_claude_client, _get_db_and_repo, _get_notifier

logger = structlog.get_logger()


async def job_generate(count: int = 2) -> dict:
    """자동 글 생성 작업

    흐름: DB에서 selected 상위 N개 → Pipeline.run() → mark_raw_topic_used

    Args:
        count: 생성할 글 수

    Returns:
        {"attempted": int, "success": int, "failed": int}
    """
    lock = get_job_lock("generate")
    if lock.locked():
        logger.warning("job_generate.already_running")
        return {"skipped": True}

    async with lock:
        job_logger = logger.bind(job="generate")
        job_logger.info("job_generate.start", count=count)

        try:
            client = _get_claude_client()
            db, repo = _get_db_and_repo()

            selected = repo.get_raw_topics_by_status("selected")
            if not selected:
                job_logger.info("job_generate.no_topics")
                return {"attempted": 0, "success": 0, "failed": 0}

            selected.sort(
                key=lambda x: x.curator_score or 0, reverse=True
            )
            targets = selected[:count]

            notifier = _get_notifier()

            from pipeline import Pipeline

            success_count = 0
            failed_count = 0

            for rt in targets:
                title = rt.title_ko or rt.title
                try:
                    pipe = Pipeline(
                        client, db_manager=db, notifier=notifier
                    )
                    result = await pipe.run(
                        topic=title,
                        content_type=(
                            rt.recommended_type or "news_briefing"
                        ),
                        category=(
                            rt.recommended_category or "ai_products"
                        ),
                        keywords=[],
                        source=rt.source,
                        source_url=rt.url,
                    )
                    repo.mark_raw_topic_used(
                        rt.id, result.topic.topic_id
                    )
                    success_count += 1
                    job_logger.info(
                        "job_generate.topic_done",
                        title=title,
                        status=result.status,
                    )
                except Exception as e:
                    failed_count += 1
                    job_logger.error(
                        "job_generate.topic_failed",
                        title=title,
                        error=str(e),
                    )

            result = {
                "attempted": len(targets),
                "success": success_count,
                "failed": failed_count,
            }
            job_logger.info("job_generate.done", **result)

            if notifier:
                await notifier.send_message(
                    f"✍️ 자동 생성 완료: "
                    f"{success_count}/{len(targets)}개 성공"
                    + (
                        f", {failed_count}개 실패"
                        if failed_count else ""
                    )
                )

            return result

        except Exception as e:
            job_logger.error("job_generate.failed", error=str(e))
            notifier = _get_notifier()
            if notifier:
                await notifier.send_message(
                    f"❌ 글 생성 실패: {str(e)}"
                )
            return {"error": str(e)}


async def job_cleanup(retention_days: int = 30) -> dict:
    """오래된 raw_topics 정리

    skipped/used 상태이고 retention_days일 이상 경과한 항목 삭제

    Args:
        retention_days: 보존 기간 (일)

    Returns:
        {"deleted": int}
    """
    lock = get_job_lock("cleanup")
    if lock.locked():
        logger.warning("job_cleanup.already_running")
        return {"skipped": True}

    async with lock:
        job_logger = logger.bind(job="cleanup")
        job_logger.info(
            "job_cleanup.start", retention_days=retention_days
        )

        try:
            _, repo = _get_db_and_repo()
            deleted = repo.cleanup_old_raw_topics(retention_days)

            result = {"deleted": deleted}
            job_logger.info("job_cleanup.done", **result)
            return result

        except Exception as e:
            job_logger.error("job_cleanup.failed", error=str(e))
            return {"error": str(e)}


async def job_daily_summary() -> None:
    """일일 요약 텔레그램 알림

    오늘의 수집/큐레이션/생성/발행 결과를 요약 메시지로 전송합니다.
    """
    job_logger = logger.bind(job="daily_summary")
    job_logger.info("job_daily_summary.start")

    try:
        _, repo = _get_db_and_repo()
        stats = repo.get_daily_stats()

        today = datetime.now().strftime("%Y-%m-%d")
        message = (
            f"📊 일일 요약 ({today})\n"
            f"├ 수집: {stats['collected']}개\n"
            f"├ 선정: {stats['selected']}개\n"
            f"├ 생성: {stats['generated']}개\n"
            f"├ 발행: {stats['published']}개\n"
            f"└ 대기: {stats['pending']}개"
        )

        notifier = _get_notifier()
        if notifier:
            await notifier.send_message(message)
            job_logger.info("job_daily_summary.sent", stats=stats)
        else:
            job_logger.warning("job_daily_summary.no_notifier")

    except Exception as e:
        job_logger.error("job_daily_summary.failed", error=str(e))
