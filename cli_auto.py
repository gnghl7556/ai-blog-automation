"""
CLI 자동화 커맨드 — 수집, 큐레이션, 자동 생성, 스케줄러
cli.py에서 등록되는 서브커맨드를 정의합니다.
"""

import asyncio
import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from database.repository import ContentRepository
from pipeline import Pipeline

console = Console()


def get_claude_client():
    """Claude API 클라이언트 생성"""
    from utils.claude_client import ClaudeClient

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[red]ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다.[/red]"
        )
        raise typer.Exit(1)
    return ClaudeClient(api_key=api_key)


def get_db_manager():
    """DatabaseManager 생성"""
    from database.session import DatabaseManager

    return DatabaseManager()


def register_auto_commands(app: typer.Typer) -> None:
    """자동화 관련 CLI 커맨드를 app에 등록"""

    @app.command()
    def collect():
        """RSS 소스에서 주제를 수집하고 DB에 저장합니다."""
        console.print(Panel("RSS 주제 수집", style="bold blue"))

        async def _collect():
            client = get_claude_client()
            db = get_db_manager()
            db.create_tables()
            repo = ContentRepository(db)

            from collectors.rss_collector import RSSCollector

            collector = RSSCollector()
            console.print(
                f"[dim]RSS 소스 {len(collector.sources)}개에서 수집 중...[/dim]"
            )
            raw_items = await collector.collect_all()
            console.print(f"  수집된 항목: {len(raw_items)}개")

            if not raw_items:
                console.print("[yellow]수집된 항목이 없습니다.[/yellow]")
                return

            from collectors.deduplicator import Deduplicator

            dedup = Deduplicator(db)
            unique_items = dedup.deduplicate(raw_items)
            console.print(f"  중복 제거 후: {len(unique_items)}개")

            if not unique_items:
                console.print("[yellow]모든 항목이 중복입니다.[/yellow]")
                return

            from collectors.translator import TopicTranslator

            translator = TopicTranslator(client)
            translated = await translator.translate_batch(unique_items)
            console.print(f"  번역 완료: {len(translated)}개")

            saved = repo.save_raw_topics(translated)
            console.print(f"\n[green]DB 저장 완료: {saved}개[/green]")

            table = Table(title=f"수집 결과 ({saved}개)")
            table.add_column("소스", style="cyan", max_width=15)
            table.add_column("제목", max_width=50)
            table.add_column("언어")

            for item in translated[:20]:
                title = item.title_ko or item.title
                table.add_row(item.source, title[:50], item.language)

            console.print(table)
            if len(translated) > 20:
                console.print(
                    f"[dim]  ... 외 {len(translated) - 20}개[/dim]"
                )

            console.print(
                f"\n[dim]API 비용: {client.get_cost_summary()}[/dim]"
            )

        asyncio.run(_collect())

    @app.command()
    def curate():
        """수집된 주제를 큐레이션합니다 (Claude API)."""
        console.print(Panel("주제 큐레이션", style="bold blue"))

        async def _curate():
            client = get_claude_client()
            db = get_db_manager()
            repo = ContentRepository(db)

            raw_topics = repo.get_raw_topics_by_status("collected")
            if not raw_topics:
                console.print(
                    "[yellow]큐레이션할 주제가 없습니다. "
                    "먼저 'collect'를 실행하세요.[/yellow]"
                )
                return

            console.print(f"[dim]큐레이션 대상: {len(raw_topics)}개[/dim]")

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
                        str(rt.published_at) if rt.published_at else ""
                    ),
                }
                for rt in raw_topics
            ]

            results = await curator.curate(items)

            for result in results:
                repo.update_raw_topic_curated(
                    result.raw_topic_id, result
                )

            selected = [r for r in results if r.selected]

            table = Table(
                title=f"큐레이션 결과 "
                f"({len(selected)}/{len(results)}개 선정)"
            )
            table.add_column("점수", justify="right", style="bold")
            table.add_column("제목", max_width=45)
            table.add_column("유형")
            table.add_column("선정", justify="center")

            sorted_results = sorted(
                results, key=lambda r: r.score, reverse=True
            )
            for r in sorted_results[:20]:
                rt = next(
                    (t for t in raw_topics if t.id == r.raw_topic_id),
                    None,
                )
                title = (
                    (rt.title_ko or rt.title)[:45] if rt
                    else r.raw_topic_id
                )
                selected_mark = (
                    "[green]O[/green]" if r.selected
                    else "[red]X[/red]"
                )
                score_color = (
                    "green" if r.score >= 7
                    else "yellow" if r.score >= 5
                    else "red"
                )
                table.add_row(
                    f"[{score_color}]{r.score:.1f}[/{score_color}]",
                    title,
                    r.recommended_type,
                    selected_mark,
                )

            console.print(table)
            console.print(
                f"\n[green]선정: {len(selected)}개[/green] / "
                f"제외: {len(results) - len(selected)}개"
            )
            console.print(
                f"\n[dim]API 비용: {client.get_cost_summary()}[/dim]"
            )

        asyncio.run(_curate())

    @app.command(name="generate-auto")
    def generate_auto(
        count: int = typer.Option(3, help="생성할 글 수"),
    ):
        """큐레이션된 상위 주제로 자동 글 생성합니다."""
        console.print(
            Panel(f"자동 글 생성 (최대 {count}개)", style="bold blue")
        )

        async def _generate():
            client = get_claude_client()
            db = get_db_manager()
            db.create_tables()
            repo = ContentRepository(db)

            selected = repo.get_raw_topics_by_status("selected")
            if not selected:
                console.print(
                    "[yellow]선정된 주제가 없습니다. "
                    "먼저 'curate'를 실행하세요.[/yellow]"
                )
                return

            selected.sort(
                key=lambda x: x.curator_score or 0, reverse=True
            )
            targets = selected[:count]

            console.print(f"[dim]생성 대상: {len(targets)}개[/dim]")

            notifier = None
            if (
                os.getenv("TELEGRAM_BOT_TOKEN")
                and os.getenv("TELEGRAM_CHAT_ID")
            ):
                from utils.notification import TelegramNotifier

                notifier = TelegramNotifier()

            success_count = 0
            for i, rt in enumerate(targets, 1):
                title = rt.title_ko or rt.title
                console.print(
                    f"\n[bold][{i}/{len(targets)}] {title}[/bold]"
                )

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
                    console.print(
                        f"  [green]완료: {result.status}[/green]"
                    )
                    success_count += 1

                except Exception as e:
                    console.print(f"  [red]실패: {str(e)}[/red]")

            console.print(
                f"\n[bold green]자동 생성 완료: "
                f"{success_count}/{len(targets)}개[/bold green]"
            )
            console.print(
                f"\n[dim]API 비용: {client.get_cost_summary()}[/dim]"
            )

        asyncio.run(_generate())

    @app.command(name="scheduler")
    def run_scheduler():
        """자동 스케줄러 시작 (수집+큐레이션+생성+승인봇)"""
        console.print(Panel(
            "자동 스케줄러 시작\n"
            "수집(06:00) → 큐레이션(06:30) → 생성(07:00) → 승인 대기\n"
            "Ctrl+C로 종료",
            style="bold blue",
        ))

        async def _run_scheduler():
            from scheduler.runner import SchedulerRunner

            runner = SchedulerRunner()

            for info in runner.scheduler.get_next_runs():
                console.print(
                    f"  [dim]{info['job']}: {info['next_run']}[/dim]"
                )

            try:
                await runner.start()
            except KeyboardInterrupt:
                await runner.stop()

        try:
            asyncio.run(_run_scheduler())
        except KeyboardInterrupt:
            console.print("\n[yellow]스케줄러 종료됨[/yellow]")

    @app.command(name="schedule-status")
    def schedule_status():
        """스케줄 상태 및 다음 실행 시간 확인"""
        from scheduler.scheduler import BlogScheduler

        try:
            sched = BlogScheduler()
            sched.setup_jobs()
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

        next_runs = sched.get_next_runs()
        sched.stop()

        if not next_runs:
            console.print(
                "[yellow]등록된 스케줄 작업이 없습니다.[/yellow]"
            )
            return

        table = Table(title="스케줄 상태")
        table.add_column("작업", style="cyan")
        table.add_column("설명", max_width=30)
        table.add_column("다음 실행", justify="right")
        table.add_column("트리거")

        for info in next_runs:
            next_run = (
                info["next_run"].strftime("%Y-%m-%d %H:%M:%S")
                if info["next_run"] else "-"
            )
            table.add_row(
                info["job"],
                info["description"],
                next_run,
                info["trigger"],
            )

        console.print(table)
