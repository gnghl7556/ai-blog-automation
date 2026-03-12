"""
스케줄 작업 정의 — 수집, 큐레이션
각 작업은 독립 async 함수로, APScheduler에서 호출됩니다.
생성/정리/요약은 jobs_generate.py에 정의됩니다.
"""

import asyncio
import os

import structlog

logger = structlog.get_logger()

# 작업별 Lock (동시 실행 방지)
_locks: dict[str, asyncio.Lock] = {}


def get_job_lock(job_name: str) -> asyncio.Lock:
    """작업별 Lock 반환 (싱글턴)

    Args:
        job_name: 작업 이름

    Returns:
        해당 작업의 asyncio.Lock
    """
    if job_name not in _locks:
        _locks[job_name] = asyncio.Lock()
    return _locks[job_name]


def _get_claude_client():
    """ClaudeClient 생성 (env 기반)

    Raises:
        ValueError: ANTHROPIC_API_KEY가 설정되지 않았거나 빈 문자열일 때
    """
    from utils.claude_client import ClaudeClient

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key.strip():
        raise ValueError(
            "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다."
        )
    return ClaudeClient(api_key=api_key)


def _get_db_and_repo():
    """DatabaseManager + ContentRepository 생성"""
    from database.session import DatabaseManager
    from database.repository import ContentRepository

    db = DatabaseManager()
    repo = ContentRepository(db)
    return db, repo


def _get_notifier():
    """TelegramNotifier 생성 (설정 있을 때)"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        from utils.notification import TelegramNotifier
        return TelegramNotifier()
    return None


async def job_collect() -> dict:
    """RSS 수집 작업

    흐름: RSSCollector → Deduplicator → TopicTranslator → DB 저장

    Returns:
        {"collected": int, "unique": int, "saved": int}
    """
    lock = get_job_lock("collect")
    if lock.locked():
        logger.warning("job_collect.already_running")
        return {"skipped": True}

    async with lock:
        job_logger = logger.bind(job="collect")
        job_logger.info("job_collect.start")

        try:
            client = _get_claude_client()
            db, repo = _get_db_and_repo()

            from collectors.rss_collector import RSSCollector
            from collectors.deduplicator import Deduplicator
            from collectors.translator import TopicTranslator

            collector = RSSCollector()
            raw_items = await collector.collect_all()

            if not raw_items:
                job_logger.info("job_collect.no_items")
                return {"collected": 0, "unique": 0, "saved": 0}

            dedup = Deduplicator(db)
            unique_items = dedup.deduplicate(raw_items)

            if not unique_items:
                job_logger.info("job_collect.all_duplicates")
                return {
                    "collected": len(raw_items),
                    "unique": 0,
                    "saved": 0,
                }

            translator = TopicTranslator(client)
            translated = await translator.translate_batch(
                unique_items
            )

            saved = repo.save_raw_topics(translated)

            result = {
                "collected": len(raw_items),
                "unique": len(unique_items),
                "saved": saved,
            }
            job_logger.info("job_collect.done", **result)

            notifier = _get_notifier()
            if notifier:
                await notifier.send_message(
                    f"📥 수집 완료: {saved}개 저장 "
                    f"(수집 {len(raw_items)} → "
                    f"중복제거 {len(unique_items)})"
                )

            return result

        except Exception as e:
            job_logger.error("job_collect.failed", error=str(e))
            notifier = _get_notifier()
            if notifier:
                await notifier.send_message(
                    f"❌ 수집 실패: {str(e)}"
                )
            return {"error": str(e)}


async def job_curate() -> dict:
    """큐레이션 작업

    흐름: DB에서 collected 로드 → CuratorAgent.curate() → DB 업데이트

    Returns:
        {"total": int, "selected": int}
    """
    lock = get_job_lock("curate")
    if lock.locked():
        logger.warning("job_curate.already_running")
        return {"skipped": True}

    async with lock:
        job_logger = logger.bind(job="curate")
        job_logger.info("job_curate.start")

        try:
            client = _get_claude_client()
            _, repo = _get_db_and_repo()

            raw_topics = repo.get_raw_topics_by_status("collected")
            if not raw_topics:
                job_logger.info("job_curate.no_topics")
                return {"total": 0, "selected": 0}

            from agents.curator_agent import CuratorAgent

            curator = CuratorAgent(client)
            items = [
                {
                    "id": rt.id,
                    "title": rt.title,
                    "title_ko": rt.title_ko or rt.title,
                    "summary_ko": rt.summary_ko or rt.summary,
                    "source": rt.source,
                    "published_at": (
                        str(rt.published_at)
                        if rt.published_at else ""
                    ),
                }
                for rt in raw_topics
            ]

            results = await curator.curate(items)

            for r in results:
                repo.update_raw_topic_curated(
                    r.raw_topic_id, r
                )

            selected_count = sum(
                1 for r in results if r.selected
            )
            result = {
                "total": len(results),
                "selected": selected_count,
            }
            job_logger.info("job_curate.done", **result)

            notifier = _get_notifier()
            if notifier:
                await notifier.send_message(
                    f"📋 큐레이션 완료: "
                    f"{selected_count}/{len(results)}개 선정"
                )

            return result

        except Exception as e:
            job_logger.error("job_curate.failed", error=str(e))
            notifier = _get_notifier()
            if notifier:
                await notifier.send_message(
                    f"❌ 큐레이션 실패: {str(e)}"
                )
            return {"error": str(e)}


# jobs_generate.py에서 정의된 함수 re-export
from scheduler.jobs_generate import (  # noqa: E402, F401
    job_generate,
    job_cleanup,
    job_daily_summary,
)
