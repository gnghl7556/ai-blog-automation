"""
WritingAgent — 플랫폼별 글 작성 에이전트
페르소나 프롬프트를 로드하여 네이버/티스토리 각각의 톤으로 글을 작성합니다.
"""

import re
import uuid

import structlog

from agents.base_agent import BaseAgent, AgentError
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    PlatformOutline,
    PlatformDraft,
)
from utils.text_utils import count_chars, extract_image_placeholders

logger = structlog.get_logger()


class WritingAgent(BaseAgent):
    """플랫폼별 글 작성 에이전트

    아웃라인과 페르소나를 기반으로 네이버/티스토리
    각각의 톤과 깊이에 맞는 블로그 글을 작성합니다.
    """

    def __init__(self, claude_client):
        super().__init__(name="writing_agent", claude_client=claude_client)

    async def write(
        self,
        outline: PlatformOutline,
        platform: str,
        topic: TopicPackage,
        research: ResearchNote,
    ) -> PlatformDraft:
        """아웃라인 기반으로 플랫폼별 글 작성

        Args:
            outline: 플랫폼별 아웃라인 (섹션, 제목 후보 등)
            platform: "naver" 또는 "tistory"
            topic: 주제 패키지
            research: 리서치 노트

        Returns:
            PlatformDraft: 작성된 초안

        Raises:
            AgentError: 글 작성 실패 시
        """
        if platform not in ("naver", "tistory"):
            raise AgentError(
                self.name, "write", f"지원하지 않는 플랫폼: {platform}"
            )

        self.logger.info(
            "write.start",
            topic_id=topic.topic_id,
            platform=platform,
            sections=len(outline.sections),
        )

        persona_prompt = self.load_persona(platform)
        user_prompt = self._build_user_prompt(outline, topic, research, platform)

        response = await self.claude_call(
            system=persona_prompt,
            user=user_prompt,
            max_tokens=4096,
            temperature=0.7,
        )

        draft = self._parse_response(response, topic, platform)

        self.logger.info(
            "write.complete",
            topic_id=topic.topic_id,
            platform=platform,
            word_count=draft.word_count,
            images=len(draft.image_placeholders),
        )
        return draft

    def _build_user_prompt(
        self,
        outline: PlatformOutline,
        topic: TopicPackage,
        research: ResearchNote,
        platform: str,
    ) -> str:
        """글 작성용 사용자 프롬프트 생성"""
        # 아웃라인 포맷팅
        sections_text = ""
        for i, section in enumerate(outline.sections, start=1):
            points = "\n".join(f"  - {p}" for p in section.key_points)
            refs = ""
            if section.references:
                refs = "\n  참고: " + ", ".join(section.references)
            sections_text += f"\n{i}. {section.title}\n{points}{refs}\n"

        # 리서치 데이터 포맷팅
        facts = "\n".join(
            f"- {f.get('fact', '')} (출처: {f.get('source', '미상')}, "
            f"신뢰도: {f.get('reliability', '중')})"
            for f in research.key_facts
        ) if research.key_facts else "(없음)"

        stats = "\n".join(
            f"- {s.get('stat', '')} (출처: {s.get('source', '미상')})"
            for s in research.statistics
        ) if research.statistics else "(없음)"

        angles = (
            research.naver_angles if platform == "naver"
            else research.tistory_angles
        )
        angles_text = ", ".join(angles) if angles else "(없음)"

        min_len, max_len = outline.target_length

        title_candidates = "\n".join(
            f"  - {t}" for t in outline.title_candidates
        )

        return f"""아래 아웃라인을 바탕으로 블로그 글을 작성해주세요.

[주제 정보]
주제: {topic.title}
카테고리: {topic.category}
글 유형: {topic.content_type}
키워드: {', '.join(topic.keywords)}

[제목 후보]
{title_candidates}
→ 위 후보 중 하나를 선택하거나 더 나은 제목을 만들어주세요.

[아웃라인]
{sections_text}

[참고 자료]
핵심 팩트:
{facts}

통계 데이터:
{stats}

관점 포인트: {angles_text}

[작성 규칙]
- 글자 수: {min_len}~{max_len}자
- 이미지 삽입 위치를 [이미지: 설명] 형식으로 표시 (3~5개)
- 각 섹션에 소제목 포함
- {outline.tone_notes or '페르소나에 맞는 톤 유지'}

첫 줄에 선택한 제목을 쓰고, 그 다음 줄부터 본문을 작성해주세요."""

    def _parse_response(
        self,
        response: str,
        topic: TopicPackage,
        platform: str,
    ) -> PlatformDraft:
        """Claude 응답에서 제목, 본문, 이미지 위치 추출"""
        lines = response.strip().split("\n", 1)

        title = lines[0].strip().strip("#").strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        image_placeholders = extract_image_placeholders(body)

        content_id = f"{platform}_{topic.topic_id}_{uuid.uuid4().hex[:8]}"

        return PlatformDraft(
            content_id=content_id,
            topic_id=topic.topic_id,
            platform=platform,
            title=title,
            body=body,
            word_count=count_chars(body),
            image_placeholders=image_placeholders,
        )
