"""
SEOAgent — SEO 최적화 에이전트
네이버(C-Rank/D.I.A.) / 티스토리(구글 SEO) 각각에 최적화합니다.
"""

import json

import structlog

from agents.base_agent import BaseAgent, AgentError
from agents.data_models import EditResult, SEOResult

logger = structlog.get_logger()


class SEOAgent(BaseAgent):
    """SEO 최적화 에이전트

    편집 완료된 글에 플랫폼별 SEO 최적화를 적용합니다.
    - 네이버: 검색 키워드, 소제목, 태그 최적화
    - 티스토리: 메타 태그, 구조화 데이터, 태그 최적화
    """

    def __init__(self, claude_client):
        super().__init__(name="seo_agent", claude_client=claude_client)

    async def optimize(
        self,
        edit_result: EditResult,
        keywords: list[str],
    ) -> SEOResult:
        """SEO 최적화 수행

        Args:
            edit_result: 편집 완료된 글
            keywords: 주제 키워드 목록

        Returns:
            SEOResult: SEO 최적화 결과
        """
        platform = edit_result.platform
        self.logger.info(
            "seo.start",
            content_id=edit_result.content_id,
            platform=platform,
        )

        seo_prompt = self.load_prompt(f"seo/seo_{platform}.yaml")

        user_prompt = self._build_user_prompt(
            edit_result, keywords, platform
        )

        response = await self.claude_call(
            system=seo_prompt,
            user=user_prompt,
            temperature=0.3,
        )

        result = self._parse_response(
            response, edit_result.content_id, platform
        )

        self.logger.info(
            "seo.complete",
            content_id=edit_result.content_id,
            platform=platform,
            seo_score=result.seo_score,
            tags_count=len(result.tags),
        )
        return result

    def _build_user_prompt(
        self,
        edit_result: EditResult,
        keywords: list[str],
        platform: str,
    ) -> str:
        """SEO 최적화 프롬프트 생성"""
        return f"""아래 블로그 글을 SEO 최적화해주세요.

[플랫폼] {platform}
[키워드] {', '.join(keywords)}

[글 본문]
{edit_result.final_draft}

반드시 JSON 형식으로 응답해주세요."""

    def _parse_response(
        self, response: str, content_id: str, platform: str
    ) -> SEOResult:
        """Claude 응답을 SEOResult로 파싱"""
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

        return SEOResult(
            content_id=content_id,
            platform=platform,
            title_final=data.get("optimized_title", ""),
            optimized_body=data.get("optimized_body", ""),
            seo_score=float(data.get("seo_score", 7.0)),
            tags=data.get("tags", []),
            meta_description=data.get("meta_description"),
            schema_markup=data.get("schema_markup"),
        )
