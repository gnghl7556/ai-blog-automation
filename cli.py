"""
AI Blog Automation — CLI 진입점
Phase 1 MVP: 주제를 수동 입력하면 양 플랫폼 글을 자동 생성합니다.
"""

import asyncio
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils.claude_client import ClaudeClient
from database.models import init_db
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


@app.command()
def init():
    """프로젝트 초기화 (DB 생성, 디렉토리 확인)"""
    console.print(Panel("AI Blog Automation 초기화", style="bold blue"))

    Path("data").mkdir(exist_ok=True)
    engine = init_db()
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
        pipe = Pipeline(client)

        result = await pipe.run(
            topic=topic,
            content_type=content_type,
            category=category,
            keywords=keyword_list,
        )

        # 결과 출력
        _print_result(result, client)

    asyncio.run(_run())


def _print_result(result, client: ClaudeClient) -> None:
    """파이프라인 결과를 Rich 테이블로 출력"""
    qr = result.quality_report

    # 품질 리포트 테이블
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

    console.print(table)

    # 결과 요약
    status_color = "green" if result.status == "success" else "red"
    console.print(f"\n[{status_color}]결과: {result.status.upper()}[/{status_color}]")

    console.print(f"\n[bold]네이버:[/bold] {result.naver_edited.final_draft[:100]}...")
    console.print(f"[bold]티스토리:[/bold] {result.tistory_edited.final_draft[:100]}...")

    if qr.issues:
        console.print("\n[yellow]이슈:[/yellow]")
        for issue in qr.issues:
            console.print(f"  - {issue}")

    # 비용
    console.print(f"\n[dim]API 비용: {client.get_cost_summary()}[/dim]")


@app.command()
def cost():
    """이번 달 API 비용 확인"""
    client = get_claude_client()
    summary = client.get_cost_summary()
    console.print(Panel("API 비용 요약", style="bold blue"))
    console.print(summary)


@app.command()
def status():
    """파이프라인 상태 확인"""
    console.print(Panel("파이프라인 상태", style="bold blue"))
    console.print("[green]Phase 1 MVP 구현 완료[/green]")
    console.print("  python cli.py generate '주제' 로 글 생성 가능")


if __name__ == "__main__":
    app()
