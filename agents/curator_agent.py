"""
CuratorAgent — 수집된 주제를 큐레이션하는 에이전트
6가지 기준으로 주제를 평가하고 점수를 부여합니다.
"""

import json

from agents.base_agent import BaseAgent
from agents.data_models import RawTopicData, CurationResult
from utils.claude_client import ClaudeClient

CHUNK_SIZE = 15

# 기준별 가중치
WEIGHTS = {
    "korean_interest": 0.25,
    "popularity": 0.20,
    "timeliness": 0.20,
    "blog_fit": 0.15,
    "differentiation": 0.10,
    "trend_relevance": 0.10,
}

CURATE_SYSTEM = """당신은 한국 AI 블로그 편집장입니다.
주제를 6가지 기준으로 평가하고, 각 기준에 0~10점 점수를 매기세요.

## 평가 기준
1. korean_interest: 한국 독자가 궁금해할 만한 주제인가?
2. popularity: 완전 일반인도 관심 가질 만한가?
3. timeliness: 지금 다뤄야 의미 있는 타이밍인가?
4. blog_fit: AI 제품/기술/활용 카테고리에 맞는가?
5. differentiation: 이미 한국어 블로그에 많이 다뤄진 주제가 아닌가?
6. trend_relevance: 검색 트렌드 상승 키워드와 관련 있는가?

## 블로그 유형 (recommended_type)
- news_briefing: 뉴스 브리핑
- tool_review: 도구 리뷰
- comparison: 비교 분석
- tech_explainer: 기술 설명
- trend_analysis: 트렌드 분석

## 카테고리 (recommended_category)
- ai_products: AI 제품/서비스
- ai_technology: AI 기술
- ai_practical: AI 활용

## 응답 형식 (JSON 배열)
[
  {
    "id": "주제 ID",
    "scores": {
      "korean_interest": 8,
      "popularity": 7,
      "timeliness": 9,
      "blog_fit": 8,
      "differentiation": 6,
      "trend_relevance": 7
    },
    "reason": "선정/제외 이유 (1-2문장)",
    "recommended_type": "news_briefing",
    "recommended_category": "ai_products"
  }
]"""


class CuratorAgent(BaseAgent):
    """수집된 주제를 큐레이션하는 에이전트

    Args:
        claude_client: ClaudeClient 인스턴스
    """

    SCORE_THRESHOLD = 7.0

    def __init__(self, claude_client: ClaudeClient):
        super().__init__(name="curator", claude_client=claude_client)

    async def curate(
        self, items: list[dict]
    ) -> list[CurationResult]:
        """주제 배치 큐레이션

        Args:
            items: 평가할 주제 리스트
                   [{"id": "...", "title": "...", "title_ko": "...",
                     "summary_ko": "...", "source": "...",
                     "published_at": "..."}, ...]

        Returns:
            CurationResult 리스트
        """
        if not items:
            return []

        all_results: list[CurationResult] = []

        for i in range(0, len(items), CHUNK_SIZE):
            chunk = items[i : i + CHUNK_SIZE]
            results = await self._curate_chunk(chunk)
            all_results.extend(results)

        self.logger.info(
            "curator.curate_done",
            total=len(all_results),
            selected=sum(1 for r in all_results if r.selected),
        )
        return all_results

    async def _curate_chunk(
        self, chunk: list[dict]
    ) -> list[CurationResult]:
        """청크 단위 큐레이션 (최대 15개)

        Args:
            chunk: 평가할 주제 청크

        Returns:
            CurationResult 리스트
        """
        user_prompt = json.dumps(chunk, ensure_ascii=False, default=str)

        try:
            response = await self.claude_call(
                system=CURATE_SYSTEM,
                user=user_prompt,
                max_tokens=4096,
                temperature=0.5,
            )
            return self._parse_response(response, chunk)

        except Exception as e:
            self.logger.error(
                "curator.chunk_failed",
                error=str(e),
            )
            return [
                CurationResult(
                    raw_topic_id=item.get("id", ""),
                    score=0.0,
                    reason=f"큐레이션 실패: {str(e)}",
                    selected=False,
                )
                for item in chunk
            ]

    def _parse_response(
        self, response: str, chunk: list[dict]
    ) -> list[CurationResult]:
        """Claude 응답을 CurationResult 리스트로 파싱

        Args:
            response: Claude API 응답 텍스트
            chunk: 원본 주제 청크 (ID 매핑용)

        Returns:
            CurationResult 리스트
        """
        try:
            # JSON 배열 추출 (응답에 마크다운 블록이 있을 수 있음)
            text = response.strip()
            if "```" in text:
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            parsed = json.loads(text)
        except json.JSONDecodeError:
            self.logger.error(
                "curator.json_parse_error",
                response=response[:300],
            )
            return [
                CurationResult(
                    raw_topic_id=item.get("id", ""),
                    score=0.0,
                    reason="JSON 파싱 실패",
                    selected=False,
                )
                for item in chunk
            ]

        results = []
        for item in parsed:
            scores = item.get("scores", {})
            total = self._calculate_weighted_score(scores)
            selected = total >= self.SCORE_THRESHOLD

            results.append(
                CurationResult(
                    raw_topic_id=item.get("id", ""),
                    score=round(total, 1),
                    criteria_scores=scores,
                    reason=item.get("reason", ""),
                    recommended_type=item.get(
                        "recommended_type", "news_briefing"
                    ),
                    recommended_category=item.get(
                        "recommended_category", "ai_products"
                    ),
                    selected=selected,
                )
            )

        return results

    def _calculate_weighted_score(
        self, scores: dict[str, float]
    ) -> float:
        """가중 평균 점수 계산

        Args:
            scores: 기준별 점수 딕셔너리

        Returns:
            가중 평균 점수 (0~10)
        """
        total = 0.0
        weight_sum = 0.0

        for criterion, weight in WEIGHTS.items():
            if criterion in scores:
                total += scores[criterion] * weight
                weight_sum += weight

        if weight_sum == 0:
            return 0.0

        return total / weight_sum
