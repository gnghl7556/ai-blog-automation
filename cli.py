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

from utils.claude_client import ClaudeClient
from database.models import init_db

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

    # DB 생성
    Path("data").mkdir(exist_ok=True)
    engine = init_db()
    console.print("[green]✅ 데이터베이스 생성 완료[/green]")

    # 필수 디렉토리 확인
    for d in ["logs", "logs/costs", "data", "templates/thumbnails/assets"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    console.print("[green]✅ 디렉토리 확인 완료[/green]")

    # .env 확인
    if Path(".env").exists():
        console.print("[green]✅ .env 파일 존재[/green]")
    else:
        console.print("[yellow]⚠️ .env 파일 없음. .env.example을 복사하세요.[/yellow]")

    console.print("\n[bold green]초기화 완료![/bold green]")


@app.command()
def generate(
    topic: str = typer.Argument(..., help="글 주제"),
    content_type: str = typer.Option("news_briefing", help="글 유형 (news_briefing/tool_review/comparison/tech_explainer/trend_analysis)"),
    keywords: str = typer.Option("", help="키워드 (쉼표 구분)"),
):
    """주제를 입력받아 네이버+티스토리 글을 자동 생성합니다."""
    console.print(Panel(f"글 생성 시작: {topic}", style="bold blue"))

    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

    async def _run():
        client = get_claude_client()

        # TODO: Phase 1 구현 후 활성화
        # 1. 리서치 에이전트
        # 2. 관점 분화
        # 3. 네이버 작성 + 티스토리 작성 (병렬)
        # 4. 네이버 편집 + 티스토리 편집 (병렬)
        # 5. 품질 검사
        # 6. 결과 저장

        console.print("[yellow]⚠️ Phase 1 구현 진행 중...[/yellow]")
        console.print(f"  주제: {topic}")
        console.print(f"  유형: {content_type}")
        console.print(f"  키워드: {keyword_list}")

        # 간단한 테스트: Claude API 연결 확인
        try:
            result = await client.call(
                system="당신은 AI 블로그 작가입니다.",
                user=f"'{topic}'에 대해 한 줄로 요약해주세요.",
                caller="cli_test",
            )
            console.print(f"\n[green]✅ Claude API 연결 성공[/green]")
            console.print(f"  응답: {result[:100]}...")
            console.print(f"\n  비용: {client.get_cost_summary()}")
        except Exception as e:
            console.print(f"[red]❌ Claude API 에러: {e}[/red]")

    asyncio.run(_run())


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
    console.print("[yellow]⚠️ Phase 2 이후 구현 예정[/yellow]")


if __name__ == "__main__":
    app()
