"""
QualityChecker — 품질 게이트 + 유사도 검사
네이버/티스토리 글의 최종 품질을 검증하고
플랫폼 간 유사도가 임계값 이하인지 확인합니다.
"""

from dataclasses import dataclass

import structlog

from agents.data_models import EditResult
from utils.text_utils import calculate_similarity, strip_html_tags

logger = structlog.get_logger()


@dataclass
class QualityReport:
    """품질 검사 결과 리포트"""

    naver_score: float
    tistory_score: float
    naver_passed: bool
    tistory_passed: bool
    similarity: float
    similarity_passed: bool
    all_passed: bool
    issues: list[str]


class QualityChecker:
    """품질 게이트 + 유사도 검사

    EditorAgent의 편집 결과를 받아서 최종 발행 가능 여부를 판단합니다.

    검사 항목:
    1. 네이버 글 품질 점수 >= quality_threshold
    2. 티스토리 글 품질 점수 >= quality_threshold
    3. 네이버/티스토리 글 간 유사도 <= similarity_threshold
    """

    def __init__(
        self,
        quality_threshold: float = 7.5,
        similarity_threshold: float = 0.55,
    ):
        self.quality_threshold = quality_threshold
        self.similarity_threshold = similarity_threshold
        self.logger = logger.bind(module="quality_checker")

    def check(
        self,
        naver_result: EditResult,
        tistory_result: EditResult,
    ) -> QualityReport:
        """네이버/티스토리 편집 결과에 대한 최종 품질 검사

        Args:
            naver_result: 네이버 편집 결과
            tistory_result: 티스토리 편집 결과

        Returns:
            QualityReport: 검사 결과 리포트
        """
        issues: list[str] = []

        # 1. 개별 품질 검사
        naver_passed = naver_result.quality_score >= self.quality_threshold
        tistory_passed = tistory_result.quality_score >= self.quality_threshold

        if not naver_passed:
            issues.append(
                f"네이버 품질 미달: {naver_result.quality_score:.1f} "
                f"(기준: {self.quality_threshold})"
            )
        if not tistory_passed:
            issues.append(
                f"티스토리 품질 미달: {tistory_result.quality_score:.1f} "
                f"(기준: {self.quality_threshold})"
            )

        # 2. 유사도 검사
        naver_text = strip_html_tags(naver_result.final_draft)
        tistory_text = strip_html_tags(tistory_result.final_draft)
        similarity = calculate_similarity(naver_text, tistory_text)
        similarity_passed = similarity <= self.similarity_threshold

        if not similarity_passed:
            issues.append(
                f"플랫폼 간 유사도 초과: {similarity:.2f} "
                f"(기준: {self.similarity_threshold} 이하)"
            )

        all_passed = naver_passed and tistory_passed and similarity_passed

        self.logger.info(
            "quality.check",
            naver_score=naver_result.quality_score,
            tistory_score=tistory_result.quality_score,
            similarity=round(similarity, 3),
            all_passed=all_passed,
        )

        return QualityReport(
            naver_score=naver_result.quality_score,
            tistory_score=tistory_result.quality_score,
            naver_passed=naver_passed,
            tistory_passed=tistory_passed,
            similarity=round(similarity, 3),
            similarity_passed=similarity_passed,
            all_passed=all_passed,
            issues=issues,
        )
