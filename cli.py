"""
AI Blog Automation — CLI 진입점
주제를 수동 입력하면 양 플랫폼 글을 자동 생성하고,
DB 저장 → 승인 → 발행까지 처리합니다.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils.claude_client import ClaudeClient
from database.session import DatabaseManager
from database.repository import ContentRepository
from database.models import TopicStatus
from pipeline import Pipeline

load_dotenv()
app = typer.Typer(help="AI Blog Automation CLI")
console = Console()


def get_claude_client() -> ClaudeClient:
    """Claude API 클라이언트 생성"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다.[/red]")
        raise typer.Exit(1)
    return ClaudeClient(api_key=api_key)


def get_db_manager() -> DatabaseManager:
    """DatabaseManager 생성"""
    return DatabaseManager()


@app.command()
def init():
    """프로젝트 초기화 (DB 생성, 디렉토리 확인)"""
    console.print(Panel("AI Blog Automation 초기화", style="bold blue"))

    Path("data").mkdir(exist_ok=True)
    db = get_db_manager()
    db.create_tables()
    console.print("[green]DB 생성 완료[/green]")

    for d in ["logs", "logs/costs", "data", "templates/thumbnails/assets"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    console.print("[green]디렉토리 확인 완료[/green]")

    if Path(".env").exists():
        console.print("[green].env 파일 존재[/green]")
    else:
        console.print("[yellow].env 파일 없음. .env.example을 복사하세요.[/yellow]")

    console.print("\n[bold green]초기화 완료![/bold green]")


@app.command()
def generate(
    topic: str = typer.Argument(..., help="글 주제"),
    content_type: str = typer.Option(
        "news_briefing",
        help="글 유형 (news_briefing/tool_review/comparison/tech_explainer/trend_analysis)",
    ),
    category: str = typer.Option(
        "ai_products",
        help="카테고리 (ai_products/ai_technology/ai_practical)",
    ),
    keywords: str = typer.Option("", help="키워드 (쉼표 구분)"),
):
    """주제를 입력받아 네이버+티스토리 글을 자동 생성합니다."""
    console.print(Panel(f"글 생성: {topic}", style="bold blue"))

    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

    async def _run():
        client = get_claude_client()
        db = get_db_manager()
        db.create_tables()

        notifier = None
        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            from utils.notification import TelegramNotifier
            notifier = TelegramNotifier()

        pipe = Pipeline(client, db_manager=db, notifier=notifier)

        result = await pipe.run(
            topic=topic,
            content_type=content_type,
            category=category,
            keywords=keyword_list,
        )

        _print_result(result, client)

    asyncio.run(_run())


def _print_result(result, client: ClaudeClient) -> None:
    """파이프라인 결과를 Rich 테이블로 출력"""
    qr = result.quality_report

    table = Table(title="품질 리포트")
    table.add_column("항목", style="cyan")
    table.add_column("값", justify="right")
    table.add_column("통과", justify="center")

    table.add_row(
        "네이버 품질",
        f"{qr.naver_score:.1f}",
        "[green]PASS[/green]" if qr.naver_passed else "[red]FAIL[/red]",
    )
    table.add_row(
        "티스토리 품질",
        f"{qr.tistory_score:.1f}",
        "[green]PASS[/green]" if qr.tistory_passed else "[red]FAIL[/red]",
    )
    table.add_row(
        "유사도",
        f"{qr.similarity:.1%}",
        "[green]PASS[/green]" if qr.similarity_passed else "[red]FAIL[/red]",
    )

    if result.naver_seo and result.tistory_seo:
        table.add_row("네이버 SEO", f"{result.naver_seo.seo_score:.1f}", "")
        table.add_row("티스토리 SEO", f"{result.tistory_seo.seo_score:.1f}", "")

    console.print(table)

    status_color = "green" if result.status in ("success", "pending_approval") else "red"
    console.print(f"\n[{status_color}]결과: {result.status.upper()}[/{status_color}]")

    if result.naver_seo:
        console.print(f"\n[bold]네이버 제목:[/bold] {result.naver_seo.title_final}")
        console.print(f"[bold]네이버 태그:[/bold] {', '.join(result.naver_seo.tags[:5])}")
    if result.tistory_seo:
        console.print(f"[bold]티스토리 제목:[/bold] {result.tistory_seo.title_final}")
        console.print(f"[bold]티스토리 메타:[/bold] {result.tistory_seo.meta_description or '-'}")

    console.print(f"\n[dim]네이버 HTML: {len(result.naver_html)}자[/dim]")
    console.print(f"[dim]티스토리 MD:  {len(result.tistory_markdown)}자[/dim]")

    if result.naver_content_id:
        console.print(f"[dim]네이버 Content ID: {result.naver_content_id}[/dim]")
    if result.tistory_content_id:
        console.print(f"[dim]티스토리 Content ID: {result.tistory_content_id}[/dim]")
    if result.status == "pending_approval":
        console.print(
            f"\n[yellow]승인 대기 중. "
            f"'python cli.py approve {result.topic.topic_id}' 또는 "
            f"텔레그램에서 승인하세요.[/yellow]"
        )

    if qr.issues:
        console.print("\n[yellow]이슈:[/yellow]")
        for issue in qr.issues:
            console.print(f"  - {issue}")

    console.print(f"\n[dim]API 비용: {client.get_cost_summary()}[/dim]")


@app.command()
def topics(
    status: Optional[str] = typer.Option(
        None, help="상태 필터 (collected/writing/review/approved/published/rejected)",
    ),
):
    """DB에서 주제 목록을 조회합니다."""
    db = get_db_manager()
    repo = ContentRepository(db)

    if status:
        topic_list = repo.get_topics_by_status(status)
    else:
        topic_list = repo.get_all_topics()

    if not topic_list:
        console.print("[yellow]등록된 주제가 없습니다.[/yellow]")
        return

    table = Table(title=f"주제 목록 (총 {len(topic_list)}개)")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("제목", max_width=40)
    table.add_column("상태", justify="center")
    table.add_column("카테고리")
    table.add_column("생성일")

    status_colors = {
        "collected": "dim", "writing": "blue", "review": "yellow",
        "approved": "green", "published": "bold green", "rejected": "red",
    }

    for t in topic_list:
        color = status_colors.get(t.status, "white")
        created = t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "-"
        table.add_row(
            t.id, t.title[:40],
            f"[{color}]{t.status}[/{color}]",
            t.category or "-", created,
        )

    console.print(table)


@app.command()
def approve(
    topic_id: str = typer.Argument(..., help="승인할 주제 ID"),
):
    """CLI에서 직접 승인 (텔레그램 없이)"""
    db = get_db_manager()
    repo = ContentRepository(db)

    topic = repo.get_topic(topic_id)
    if not topic:
        console.print(f"[red]주제를 찾을 수 없습니다: {topic_id}[/red]")
        raise typer.Exit(1)

    if topic.status not in ("review", TopicStatus.REVIEW.value):
        console.print(
            f"[yellow]현재 상태가 '{topic.status}'입니다. "
            f"'review' 상태만 승인할 수 있습니다.[/yellow]"
        )
        raise typer.Exit(1)

    contents = repo.get_contents_by_topic(topic_id)
    for c in contents:
        repo.save_approval_log(c.id, "approved", notes="CLI 승인")

    repo.update_topic_status(topic_id, TopicStatus.APPROVED)
    console.print(f"[green]승인 완료: {topic_id} ({topic.title})[/green]")
    console.print(f"[dim]발행하려면: python cli.py publish {topic_id}[/dim]")


@app.command()
def publish(
    topic_id: str = typer.Argument(..., help="발행할 주제 ID"),
):
    """승인된 글을 네이버+티스토리에 발행합니다."""
    db = get_db_manager()
    repo = ContentRepository(db)

    topic = repo.get_topic(topic_id)
    if not topic:
        console.print(f"[red]주제를 찾을 수 없습니다: {topic_id}[/red]")
        raise typer.Exit(1)

    if topic.status not in ("approved", TopicStatus.APPROVED.value):
        console.print(
            f"[yellow]현재 상태가 '{topic.status}'입니다. "
            f"'approved' 상태만 발행할 수 있습니다.[/yellow]"
        )
        raise typer.Exit(1)

    console.print(Panel(f"발행: {topic.title}", style="bold blue"))

    async def _publish():
        client = get_claude_client()

        notifier = None
        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            from utils.notification import TelegramNotifier
            notifier = TelegramNotifier()

        pipe = Pipeline(client, db_manager=db, notifier=notifier)
        result = await pipe.publish(topic_id)

        if result.naver_publish_result:
            nr = result.naver_publish_result
            if nr.success:
                console.print(f"[green]네이버: {nr.published_url}[/green]")
            else:
                console.print(f"[red]네이버 실패: {nr.error}[/red]")

        if result.tistory_publish_result:
            tr = result.tistory_publish_result
            if tr.success:
                console.print(f"[green]티스토리: {tr.published_url}[/green]")
            else:
                console.print(f"[red]티스토리 실패: {tr.error}[/red]")

        console.print(f"\n[bold]최종 상태: {result.status.upper()}[/bold]")

    asyncio.run(_publish())


@app.command()
def cost():
    """이번 달 API 비용 확인"""
    client = get_claude_client()
    summary = client.get_cost_summary()
    console.print(Panel("API 비용 요약", style="bold blue"))
    console.print(summary)


@app.command()
def bot():
    """텔레그램 봇을 시작합니다 (Long Polling, Ctrl+C로 종료)"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        console.print(
            "[red]TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID가 "
            ".env에 설정되어야 합니다.[/red]"
        )
        raise typer.Exit(1)

    db = get_db_manager()
    db.create_tables()

    console.print(Panel(
        "텔레그램 승인 봇 시작\n"
        "승인 → 자동 발행 | 반려 → DB 상태 변경\n"
        "Ctrl+C로 종료",
        style="bold blue",
    ))

    async def _run_bot():
        from approval.bot_runner import BotRunner
        from utils.notification import TelegramNotifier

        notifier = TelegramNotifier()
        runner = BotRunner(db_manager=db, notifier=notifier)

        try:
            await runner.start()
        except KeyboardInterrupt:
            runner.stop()

    try:
        asyncio.run(_run_bot())
    except KeyboardInterrupt:
        console.print("\n[yellow]봇 종료됨[/yellow]")


@app.command()
def status():
    """파이프라인 상태 확인"""
    console.print(Panel("파이프라인 상태", style="bold blue"))
    console.print("[green]Phase 5 — 스케줄러 + 전자동 파이프라인[/green]")
    console.print("  python cli.py scheduler        — 자동 스케줄러 시작")
    console.print("  python cli.py schedule-status  — 스케줄 상태 확인")
    console.print("  python cli.py collect          — RSS 주제 수집")
    console.print("  python cli.py curate           — 주제 큐레이션")
    console.print("  python cli.py generate-auto    — 자동 글 생성")
    console.print("  python cli.py generate '주제'  — 수동 글 생성")
    console.print("  python cli.py topics           — 주제 목록 조회")
    console.print("  python cli.py approve <id>     — CLI 승인")
    console.print("  python cli.py publish <id>     — 수동 발행")
    console.print("  python cli.py bot              — 텔레그램 봇")
    console.print("  python cli.py health           — 헬스체크")
    console.print("  python cli.py db-migrate       — DB 마이그레이션 생성")
    console.print("  python cli.py db-upgrade       — DB 마이그레이션 적용")


# 자동화 커맨드 등록
from cli_auto import register_auto_commands  # noqa: E402

register_auto_commands(app)


if __name__ == "__main__":
    app()
