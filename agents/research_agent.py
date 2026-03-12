"""
ResearchAgent — 주제 리서치 에이전트
주제에 대한 핵심 팩트, 통계, 비유 소재를 수집하고
플랫폼별 관점 포인트를 생성합니다.
"""

import json
import uuid

import structlog

from agents.base_agent import BaseAgent, AgentError
from agents.data_models import TopicPackage, ResearchNote

logger = structlog.get_logger()

RESEARCH_SYSTEM_PROMPT = """당신은 AI/기술 블로그 리서치 전문가입니다.
주어진 주제에 대해 블로그 글 작성에 필요한 자료를 수집합니다.

다음 항목을 조사하세요:
1. 핵심 팩트 (3~5개): 정확한 사실 + 출처 + 신뢰도(high/medium/low)
2. 통계 데이터 (1~3개): 수치/데이터 + 출처
3. 비유 소재 (2~3개): 일반인이 이해할 수 있는 비유
4. 네이버 관점 (2~3개): 일반인 대상, "왜 중요한지", "나한테 어떤 영향이 있는지"
5. 티스토리 관점 (2~3개): IT 비개발자 대상, "실무에 어떻게 적용할지", "기술적으로 뭐가 달라졌는지"

반드시 아래 JSON 형식으로만 응답하세요:
{
  "key_facts": [
    {"fact": "설명", "source": "출처", "reliability": "high"}
  ],
  "statistics": [
    {"stat": "수치 설명", "source": "출처"}
  ],
  "analogies": ["비유1", "비유2"],
  "naver_angles": ["관점1", "관점2"],
  "tistory_angles": ["관점1", "관점2"],
  "sources": ["URL1", "URL2"]
}"""


class ResearchAgent(BaseAgent):
    """주제 리서치 에이전트

    주제에 대한 핵심 정보를 조사하고
    플랫폼별 관점 포인트를 생성합니다.
    """

    def __init__(self, claude_client):
        super().__init__(name="research_agent", claude_client=claude_client)

    async def research(self, topic: TopicPackage) -> ResearchNote:
        """주제 리서치 수행

        Args:
            topic: 주제 패키지

        Returns:
            ResearchNote: 리서치 결과
        """
        self.logger.info(
            "research.start",
            topic_id=topic.topic_id,
            title=topic.title,
        )

        user_prompt = self._build_user_prompt(topic)

        response = await self.claude_call(
            system=RESEARCH_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=4096,
            temperature=0.5,
        )

        note = self._parse_response(response, topic.topic_id)

        self.logger.info(
            "research.complete",
            topic_id=topic.topic_id,
            facts=len(note.key_facts),
            stats=len(note.statistics),
        )
        return note

    def _build_user_prompt(self, topic: TopicPackage) -> str:
        """리서치 프롬프트 생성"""
        return f"""주제: {topic.title}
카테고리: {topic.category}
글 유형: {topic.content_type}
키워드: {', '.join(topic.keywords)}
원본 소스: {topic.source}
{f'원본 URL: {topic.source_url}' if topic.source_url else ''}

위 주제에 대해 블로그 글 작성에 필요한 리서치를 수행해주세요.
반드시 JSON 형식으로만 응답해주세요."""

    def _parse_response(self, response: str, topic_id: str) -> ResearchNote:
        """Claude 응답을 ResearchNote로 파싱"""
        try:
            json_text = response
            if "```" in response:
                for block in response.split("```"):
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

        return ResearchNote(
            topic_id=topic_id,
            key_facts=data.get("key_facts", []),
            statistics=data.get("statistics", []),
            analogies=data.get("analogies", []),
            naver_angles=data.get("naver_angles", []),
            tistory_angles=data.get("tistory_angles", []),
            sources=data.get("sources", []),
        )
