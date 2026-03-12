"""
ContentSplitter — 관점 분화 에이전트
같은 주제를 네이버/티스토리 각각의 관점과 깊이로 분화합니다.
네이버: "이해"시키기 (일반인 대상, 비유 중심)
티스토리: "학습"시키기 (IT 비개발자 대상, 전문 분석)
"""

import json
from typing import Optional

import structlog

from agents.base_agent import BaseAgent, AgentError
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    SplitOutlines,
    PlatformOutline,
    SectionOutline,
)

logger = structlog.get_logger()

SPLIT_SYSTEM_PROMPT = """당신은 콘텐츠 관점 분화 전문가입니다.
같은 주제를 두 가지 완전히 다른 관점으로 나누어 아웃라인을 작성합니다.

■ 네이버 블로그 (이해시키기)
- 독자: 완전 일반인 (부모님, 비IT 직장인)
- 관점: 일상 비유, 쉬운 설명, "이게 왜 중요한지"
- 소제목: 네이버 검색 키워드 포함
- 깊이: 넓고 얕게, 핵심만

■ 티스토리 (학습시키기)
- 독자: IT 종사 비개발자 (기획자, 마케터, PM)
- 관점: 업계 분석, 실무 적용, 비교 분석
- 소제목: 정보 전달형, 명확한 구조
- 깊이: 좁고 깊게, 디테일

■ 핵심 규칙
- 두 아웃라인의 관점이 완전히 달라야 합니다 (유사도 55% 이하)
- 같은 팩트를 다루더라도 프레이밍이 달라야 합니다

반드시 아래 JSON 형식으로만 응답하세요:
{
  "naver": {
    "title_candidates": ["제목1", "제목2", "제목3"],
    "sections": [
      {"title": "소제목", "key_points": ["포인트1", "포인트2"], "references": []}
    ],
    "target_length": [2000, 3000],
    "tone_notes": "톤 관련 메모"
  },
  "tistory": {
    "title_candidates": ["제목1", "제목2", "제목3"],
    "sections": [
      {"title": "소제목", "key_points": ["포인트1", "포인트2"], "references": []}
    ],
    "target_length": [3000, 4500],
    "tone_notes": "톤 관련 메모"
  }
}"""


class ContentSplitter(BaseAgent):
    """관점 분화 에이전트

    같은 주제를 네이버/티스토리 플랫폼에 맞게
    서로 다른 관점과 깊이의 아웃라인으로 분화합니다.
    """

    def __init__(self, claude_client):
        super().__init__(name="content_splitter", claude_client=claude_client)
        settings = self.load_config("settings.yaml")
        self.similarity_threshold: float = settings["publishing"]["similarity_threshold"]

    async def split(
        self, topic: TopicPackage, research: ResearchNote
    ) -> SplitOutlines:
        """주제를 네이버/티스토리 관점으로 분화

        Args:
            topic: 주제 패키지 (제목, 카테고리, 키워드 등)
            research: 리서치 노트 (팩트, 통계, 비유 소재 등)

        Returns:
            SplitOutlines: 플랫폼별 아웃라인

        Raises:
            AgentError: 관점 분화 실패 시
        """
        self.logger.info(
            "split.start",
            topic_id=topic.topic_id,
            title=topic.title,
        )

        user_prompt = self._build_user_prompt(topic, research)

        response = await self.claude_call(
            system=SPLIT_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.8,
        )

        outlines = self._parse_response(response, topic.topic_id)

        self.logger.info(
            "split.complete",
            topic_id=topic.topic_id,
            naver_sections=len(outlines.naver.sections),
            tistory_sections=len(outlines.tistory.sections),
        )
        return outlines

    def _build_user_prompt(
        self, topic: TopicPackage, research: ResearchNote
    ) -> str:
        """Claude에게 보낼 사용자 프롬프트 생성"""
        facts_text = ""
        if research.key_facts:
            facts_text = "\n".join(
                f"- {f.get('fact', '')}" for f in research.key_facts
            )

        stats_text = ""
        if research.statistics:
            stats_text = "\n".join(
                f"- {s.get('stat', '')} (출처: {s.get('source', '미상')})"
                for s in research.statistics
            )

        return f"""주제: {topic.title}
카테고리: {topic.category}
키워드: {', '.join(topic.keywords)}
글 유형: {topic.content_type}

[리서치 결과]
핵심 팩트:
{facts_text or '(없음)'}

통계:
{stats_text or '(없음)'}

비유 소재: {', '.join(research.analogies) if research.analogies else '(없음)'}

네이버 관점 힌트: {', '.join(research.naver_angles) if research.naver_angles else '(없음)'}
티스토리 관점 힌트: {', '.join(research.tistory_angles) if research.tistory_angles else '(없음)'}

위 주제를 네이버/티스토리 각각의 관점으로 분화해주세요.
반드시 JSON 형식으로만 응답해주세요."""

    def _parse_response(self, response: str, topic_id: str) -> SplitOutlines:
        """Claude 응답을 SplitOutlines 모델로 파싱"""
        try:
            # JSON 블록 추출 (```json ... ``` 또는 순수 JSON)
            json_text = response
            if "```" in response:
                match = response.split("```")
                for block in match:
                    cleaned = block.strip()
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:].strip()
                    if cleaned.startswith("{"):
                        json_text = cleaned
                        break

            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise AgentError(
                self.name, "parse", f"JSON 파싱 실패: {e}", recoverable=True
            )

        def _parse_outline(platform_data: dict) -> PlatformOutline:
            sections = [
                SectionOutline(
                    title=s["title"],
                    key_points=s.get("key_points", []),
                    references=s.get("references", []),
                )
                for s in platform_data.get("sections", [])
            ]
            length = platform_data.get("target_length", [2000, 3000])
            return PlatformOutline(
                title_candidates=platform_data.get("title_candidates", []),
                sections=sections,
                target_length=tuple(length),
                tone_notes=platform_data.get("tone_notes"),
            )

        return SplitOutlines(
            topic_id=topic_id,
            naver=_parse_outline(data.get("naver", {})),
            tistory=_parse_outline(data.get("tistory", {})),
        )
