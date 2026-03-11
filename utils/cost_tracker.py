"""
API 비용 추적 모듈
모든 Claude API 호출의 토큰 사용량과 비용을 추적합니다.
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

# Claude Sonnet 4 가격 (2025년 기준, 1M 토큰당)
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
}


class CostTracker:
    """API 비용 실시간 추적"""

    def __init__(self, log_dir: str = "logs/costs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.daily_records: list[dict] = []

    def log(
        self,
        caller: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        elapsed_seconds: float,
    ) -> None:
        """API 호출 비용 기록"""
        pricing = PRICING.get(model, {"input": 3.0, "output": 15.0})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

        record = {
            "timestamp": datetime.now().isoformat(),
            "caller": caller,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "elapsed_seconds": round(elapsed_seconds, 1),
        }

        self.daily_records.append(record)
        self._save_to_file(record)

    def get_summary(self, period: Optional[str] = None) -> dict:
        """비용 요약 (today / month / all)"""
        records = self.daily_records
        if not records:
            return {"total_cost": 0, "total_calls": 0}

        total_cost = sum(r["cost_usd"] for r in records)
        total_input = sum(r["input_tokens"] for r in records)
        total_output = sum(r["output_tokens"] for r in records)

        # 에이전트별 비용
        by_caller = {}
        for r in records:
            caller = r["caller"]
            if caller not in by_caller:
                by_caller[caller] = {"cost": 0, "calls": 0}
            by_caller[caller]["cost"] += r["cost_usd"]
            by_caller[caller]["calls"] += 1

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_calls": len(records),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "by_caller": by_caller,
        }

    def _save_to_file(self, record: dict) -> None:
        """일별 파일에 기록"""
        today = date.today().isoformat()
        filepath = self.log_dir / f"costs_{today}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
