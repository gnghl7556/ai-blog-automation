"""
EditorAgent — 4단계 편집 파이프라인
팩트체크 → 가독성 → 톤 검사 → 맞춤법 순서로 편집합니다.
"""

import json

import structlog

from agents.base_agent import BaseAgent, AgentError
from agents.data_models import PlatformDraft, EditResult

logger = structlog.get_logger()

QUALITY_SYSTEM_PROMPT = """당신은 블로그 글 품질 평가 전문가입니다.
아래 5개 항목을 각각 10점 만점으로 평가하세요.

1. accuracy (정확성): 사실 관계가 정확한가?
2. readability (가독성): 읽기 쉽고 흐름이 자연스러운가?
3. engagement (흥미도): 독자가 끝까지 읽고 싶어하는가?
4. structure (구조): 소제목, 문단, 전환이 논리적인가?
5. tone (톤 일관성): 플랫폼 페르소나에 맞는 말투를 유지하는가?

반드시 아래 JSON 형식으로만 응답하세요:
{"accuracy": 8, "readability": 7, "engagement": 8, "structure": 9, "tone": 7}"""


class EditorAgent(BaseAgent):
    """4단계 편집 파이프라인 에이전트

    팩트체크 → 가독성 → 톤 검사 → 맞춤법 순서로
    편집하고 품질 평가를 수행합니다.
    """

    def __init__(self, claude_client):
        super().__init__(name="editor_agent", claude_client=claude_client)
        settings = self.load_config("settings.yaml")
        self.quality_threshold: float = settings["publishing"]["quality_threshold"]
        self.score_weights: dict = settings["quality"]["score_weights"]

    async def edit(self, draft: PlatformDraft) -> EditResult:
        """4단계 편집 파이프라인 실행

        Args:
            draft: 작성된 초안

        Returns:
            EditResult: 편집 결과 (수정된 글 + 품질 점수)
        """
        self.logger.info(
            "edit.start",
            content_id=draft.content_id,
            platform=draft.platform,
        )

        edit_summary = {}
        text = draft.body

        # 1단계: 팩트체크
        text, summary = await self._factcheck(text)
        edit_summary["factcheck"] = summary

        # 2단계: 가독성 개선
        text, summary = await self._improve_readability(text, draft.platform)
        edit_summary["readability"] = summary

        # 3단계: 톤 검사
        text, summary = await self._check_tone(text, draft.platform)
        edit_summary["tone"] = summary

        # 4단계: 맞춤법
        text, summary = await self._fix_grammar(text)
        edit_summary["grammar"] = summary

        # 품질 평가
        score, detail = await self._evaluate_quality(text, draft.platform)
        passed = score >= self.quality_threshold

        self.logger.info(
            "edit.complete",
            content_id=draft.content_id,
            quality_score=score,
            passed=passed,
        )

        return EditResult(
            content_id=draft.content_id,
            platform=draft.platform,
            final_draft=text,
            quality_score=score,
            quality_detail=detail,
            edit_summary=edit_summary,
            passed=passed,
        )

    async def _factcheck(self, text: str) -> tuple[str, str]:
        """1단계: 팩트체크 — 출처 없는 수치/통계 확인"""
        response = await self.claude_call(
            system=("당신은 팩트체크 전문가입니다. "
                    "아래 글에서 출처 없는 수치, 통계, 부정확한 정보를 찾아 수정하세요. "
                    "수정한 글 전체를 출력하세요. "
                    "마지막 줄에 '---' 구분선 후 수정 내역을 한 줄로 요약하세요. "
                    "수정할 내용이 없으면 원문 그대로 출력하고 '수정 없음'이라고 쓰세요."),
            user=text,
            temperature=0.3,
        )
        return self._split_text_and_summary(response)

    async def _improve_readability(
        self, text: str, platform: str
    ) -> tuple[str, str]:
        """2단계: 가독성 개선 — 문단, 전환어, 흐름"""
        platform_guide = (
            "네이버 블로그 (일반인 독자, 강연체)"
            if platform == "naver"
            else "티스토리 (IT 비개발자 독자, 전문체)"
        )
        response = await self.claude_call(
            system=(f"당신은 {platform_guide}의 가독성 전문 편집자입니다. "
                    "아래 글의 문단 길이, 전환어, 흐름을 개선하세요. "
                    "수정한 글 전체를 출력하세요. "
                    "마지막 줄에 '---' 구분선 후 수정 내역을 한 줄로 요약하세요."),
            user=text,
            temperature=0.3,
        )
        return self._split_text_and_summary(response)

    async def _check_tone(
        self, text: str, platform: str
    ) -> tuple[str, str]:
        """3단계: 톤 검사 — 플랫폼별 말투 일관성"""
        if platform == "naver":
            tone_rule = ("네이버 블로그 톤: ~거든요, ~인 거예요, ~인 거죠, ~잖아요 체. "
                         "~입니다/~합니다 체를 발견하면 강연체로 수정하세요. "
                         "전문 용어는 쉬운 말로 바꾸세요.")
        else:
            tone_rule = ("티스토리 톤: ~입니다, ~합니다 체. "
                         "~거든요/~잖아요 체를 발견하면 전문체로 수정하세요. "
                         "전문 용어는 처음 등장 시 간단한 설명을 추가하세요.")

        response = await self.claude_call(
            system=(f"당신은 톤 일관성 편집자입니다. {tone_rule} "
                    "수정한 글 전체를 출력하세요. "
                    "마지막 줄에 '---' 구분선 후 수정 내역을 한 줄로 요약하세요."),
            user=text,
            temperature=0.3,
        )
        return self._split_text_and_summary(response)

    async def _fix_grammar(self, text: str) -> tuple[str, str]:
        """4단계: 맞춤법 — 오탈자, 문법 오류 수정"""
        response = await self.claude_call(
            system=("당신은 한국어 맞춤법 전문가입니다. "
                    "아래 글의 오탈자, 문법 오류, 띄어쓰기를 수정하세요. "
                    "수정한 글 전체를 출력하세요. "
                    "마지막 줄에 '---' 구분선 후 수정 내역을 한 줄로 요약하세요."),
            user=text,
            temperature=0.2,
        )
        return self._split_text_and_summary(response)

    async def _evaluate_quality(
        self, text: str, platform: str
    ) -> tuple[float, dict]:
        """품질 평가 — 5개 항목 가중 평균"""
        platform_desc = (
            "네이버 블로그 (일반인 대상, 강연체)"
            if platform == "naver"
            else "티스토리 (IT 비개발자 대상, 전문체)"
        )
        response = await self.claude_call(
            system=QUALITY_SYSTEM_PROMPT,
            user=f"플랫폼: {platform_desc}\n\n{text}",
            temperature=0.2,
        )

        try:
            # JSON 추출
            json_text = response.strip()
            if "```" in json_text:
                for block in json_text.split("```"):
                    cleaned = block.strip().removeprefix("json").strip()
                    if cleaned.startswith("{"):
                        json_text = cleaned
                        break
            detail = json.loads(json_text)
        except json.JSONDecodeError:
            self.logger.warning("quality.parse_failed", response=response[:200])
            detail = {
                "accuracy": 7, "readability": 7,
                "engagement": 7, "structure": 7, "tone": 7,
            }

        weighted_score = sum(
            detail.get(k, 7) * w
            for k, w in self.score_weights.items()
        )
        return round(weighted_score, 2), detail

    def _split_text_and_summary(self, response: str) -> tuple[str, str]:
        """편집 응답에서 수정된 텍스트와 요약을 분리"""
        if "---" in response:
            parts = response.rsplit("---", 1)
            return parts[0].strip(), parts[1].strip()
        return response.strip(), "수정 내역 없음"
