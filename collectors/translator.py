"""
TopicTranslator — 영어 주제의 제목+요약을 한국어로 번역
Claude API를 사용하며, 배치 처리로 API 호출을 최소화합니다.
"""

import json

import structlog

from agents.data_models import RawTopicData
from utils.claude_client import ClaudeClient

logger = structlog.get_logger()

TRANSLATE_SYSTEM = """당신은 AI/기술 뉴스 전문 번역가입니다.
영어 제목과 요약을 자연스러운 한국어로 번역하세요.
고유명사(GPT, Claude, Gemini, OpenAI 등)는 그대로 유지합니다.
결과를 JSON 배열로 반환하세요.

입력 형식: [{"index": 0, "title": "...", "summary": "..."}, ...]
출력 형식: [{"index": 0, "title_ko": "...", "summary_ko": "..."}, ...]"""

CHUNK_SIZE = 20


class TopicTranslator:
    """영어 주제 한국어 번역기

    Args:
        claude_client: ClaudeClient 인스턴스
    """

    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.logger = logger.bind(module="translator")

    async def translate_batch(
        self, items: list[RawTopicData]
    ) -> list[RawTopicData]:
        """배치 번역

        영어 항목만 필터링하여 Claude API로 번역합니다.
        한국어 소스는 스킵합니다.

        Args:
            items: 번역할 RawTopicData 리스트

        Returns:
            title_ko, summary_ko가 채워진 RawTopicData 리스트
        """
        en_items = [it for it in items if it.language != "ko"]
        ko_items = [it for it in items if it.language == "ko"]

        # 한국어 소스는 title_ko = title로 설정
        for item in ko_items:
            item.title_ko = item.title
            item.summary_ko = item.summary

        if not en_items:
            self.logger.info("translator.no_english_items")
            return items

        # 청크별 번역
        for i in range(0, len(en_items), CHUNK_SIZE):
            chunk = en_items[i : i + CHUNK_SIZE]
            await self._translate_chunk(chunk)

        self.logger.info(
            "translator.done",
            translated=len(en_items),
            skipped=len(ko_items),
        )
        return items

    async def _translate_chunk(
        self, chunk: list[RawTopicData]
    ) -> None:
        """청크 단위 번역 (최대 20개, in-place 수정)

        Args:
            chunk: 번역할 RawTopicData 청크
        """
        payload = [
            {
                "index": i,
                "title": item.title,
                "summary": item.summary[:500],
            }
            for i, item in enumerate(chunk)
        ]

        try:
            response = await self.claude.call(
                system=TRANSLATE_SYSTEM,
                user=json.dumps(payload, ensure_ascii=False),
                max_tokens=2048,
                temperature=0.3,
                caller="translator",
            )

            results = json.loads(response)
            for r in results:
                idx = r.get("index", -1)
                if 0 <= idx < len(chunk):
                    chunk[idx].title_ko = r.get("title_ko", "")
                    chunk[idx].summary_ko = r.get("summary_ko", "")

        except json.JSONDecodeError:
            self.logger.error(
                "translator.json_parse_error",
                response=response[:200],
            )
        except Exception as e:
            self.logger.error(
                "translator.api_error",
                error=str(e),
            )
