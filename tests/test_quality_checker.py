"""
QualityChecker 테스트
"""

import pytest

from agents.quality_checker import QualityChecker, QualityReport
from agents.data_models import EditResult


def make_edit_result(
    platform: str,
    quality_score: float,
    final_draft: str = "",
    passed: bool = True,
) -> EditResult:
    """테스트용 EditResult 생성"""
    return EditResult(
        content_id=f"{platform}_test_001",
        platform=platform,
        final_draft=final_draft or f"{platform} 테스트 본문입니다.",
        quality_score=quality_score,
        quality_detail={"accuracy": 8, "readability": 8, "engagement": 8, "structure": 8, "tone": 8},
        edit_summary={"factcheck": "수정 없음"},
        passed=passed,
    )


class TestQualityChecker:
    def test_all_passed(self):
        """모든 검사 통과"""
        checker = QualityChecker()
        naver = make_edit_result("naver", 8.0, "네이버 블로그 글입니다. 완전히 다른 내용이에요.")
        tistory = make_edit_result("tistory", 8.5, "티스토리 전문 분석 글입니다. 기술적 관점에서 살펴봅니다.")

        report = checker.check(naver, tistory)

        assert report.all_passed is True
        assert report.naver_passed is True
        assert report.tistory_passed is True
        assert report.similarity_passed is True
        assert len(report.issues) == 0

    def test_naver_quality_fail(self):
        """네이버 품질 미달"""
        checker = QualityChecker()
        naver = make_edit_result("naver", 6.0)
        tistory = make_edit_result("tistory", 8.0, "완전히 다른 글")

        report = checker.check(naver, tistory)

        assert report.naver_passed is False
        assert report.all_passed is False
        assert any("네이버 품질 미달" in i for i in report.issues)

    def test_tistory_quality_fail(self):
        """티스토리 품질 미달"""
        checker = QualityChecker()
        naver = make_edit_result("naver", 8.0, "네이버 글")
        tistory = make_edit_result("tistory", 5.0, "티스토리 글")

        report = checker.check(naver, tistory)

        assert report.tistory_passed is False
        assert report.all_passed is False

    def test_similarity_fail(self):
        """유사도 초과"""
        checker = QualityChecker()
        same_text = "동일한 텍스트로 작성된 블로그 글입니다. AI에 대해 알아봅시다."
        naver = make_edit_result("naver", 8.0, same_text)
        tistory = make_edit_result("tistory", 8.0, same_text)

        report = checker.check(naver, tistory)

        assert report.similarity_passed is False
        assert report.similarity == 1.0
        assert report.all_passed is False
        assert any("유사도 초과" in i for i in report.issues)

    def test_custom_thresholds(self):
        """커스텀 임계값 적용"""
        checker = QualityChecker(quality_threshold=9.0, similarity_threshold=0.3)
        naver = make_edit_result("naver", 8.5, "네이버 글")
        tistory = make_edit_result("tistory", 8.5, "티스토리 글")

        report = checker.check(naver, tistory)

        assert report.naver_passed is False
        assert report.tistory_passed is False

    def test_report_has_scores(self):
        """리포트에 점수가 포함되는지"""
        checker = QualityChecker()
        naver = make_edit_result("naver", 8.0, "네이버 글입니다")
        tistory = make_edit_result("tistory", 9.0, "티스토리 글입니다")

        report = checker.check(naver, tistory)

        assert report.naver_score == 8.0
        assert report.tistory_score == 9.0
        assert isinstance(report.similarity, float)
