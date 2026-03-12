"""
PreviewGenerator — 승인 게이트용 미리보기 생성
텔레그램에 보낼 글 요약 메시지를 생성합니다.
"""

from pipeline import PipelineResult
from utils.text_utils import truncate_text


class PreviewGenerator:
    """파이프라인 결과를 텔레그램 미리보기 메시지로 변환"""

    def generate(self, result: PipelineResult) -> str:
        """승인 요청 미리보기 메시지 생성

        Args:
            result: 파이프라인 결과

        Returns:
            HTML 포맷 텔레그램 메시지
        """
        qr = result.quality_report
        naver_seo = result.naver_seo
        tistory_seo = result.tistory_seo

        naver_title = naver_seo.title_final if naver_seo else "(SEO 미적용)"
        tistory_title = tistory_seo.title_final if tistory_seo else "(SEO 미적용)"

        naver_preview = truncate_text(result.naver_edited.final_draft, 200)
        tistory_preview = truncate_text(result.tistory_edited.final_draft, 200)

        # 품질 이모지
        def _score_emoji(score: float) -> str:
            if score >= 8.5:
                return "🟢"
            if score >= 7.5:
                return "🟡"
            return "🔴"

        naver_q = result.naver_edited.quality_score
        tistory_q = result.tistory_edited.quality_score

        lines = [
            "📝 <b>새 글 승인 요청</b>",
            "",
            f"📌 주제: <b>{result.topic.title}</b>",
            f"📁 카테고리: {result.topic.category}",
            f"📋 유형: {result.topic.content_type}",
            "",
            "━━━ 네이버 ━━━",
            f"제목: {naver_title}",
            f"품질: {_score_emoji(naver_q)} {naver_q:.1f}",
            f"SEO: {naver_seo.seo_score:.1f}" if naver_seo else "",
            f"미리보기: {naver_preview}",
            "",
            "━━━ 티스토리 ━━━",
            f"제목: {tistory_title}",
            f"품질: {_score_emoji(tistory_q)} {tistory_q:.1f}",
            f"SEO: {tistory_seo.seo_score:.1f}" if tistory_seo else "",
            f"미리보기: {tistory_preview}",
            "",
            f"📊 유사도: {qr.similarity:.1%}" if qr else "",
        ]

        if qr and qr.issues:
            lines.append("")
            lines.append("⚠️ <b>이슈:</b>")
            for issue in qr.issues:
                lines.append(f"  • {issue}")

        return "\n".join(line for line in lines if line is not None)
