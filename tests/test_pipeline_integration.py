"""
Pipeline 통합 테스트 — DB 저장 + 승인 + 발행 흐름 (mock)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from database.repository import ContentRepository
from database.models import TopicStatus
from pipeline import Pipeline, PipelineResult
from agents.data_models import (
    TopicPackage,
    ResearchNote,
    SplitOutlines,
    PlatformOutline,
    SectionOutline,
    PlatformDraft,
    EditResult,
    SEOResult,
    PublishResult,
)


@pytest.fixture
def mock_client():
    """Mock ClaudeClient"""
    from utils.claude_client import ClaudeClient
    client = MagicMock(spec=ClaudeClient)
    client.call = AsyncMock(return_value="mock response")
    client.cost_tracker = MagicMock()
    return client


def _make_outline():
    return PlatformOutline(
        title_candidates=["테스트 제목"],
        sections=[SectionOutline(title="섹션1", key_points=["포인트1"])],
        target_length=(1000, 2000),
    )


def _make_draft(platform):
    return PlatformDraft(
        content_id=f"draft_{platform}",
        topic_id="test_topic",
        platform=platform,
        title=f"{platform} 제목",
        body=f"{platform} 본문",
        word_count=500,
    )


def _make_edit(platform):
    return EditResult(
        content_id=f"edit_{platform}",
        platform=platform,
        final_draft=f"{platform} 편집 본문",
        quality_score=8.0,
        quality_detail={"accuracy": 8.0},
        edit_summary={"factcheck": "OK"},
        passed=True,
    )


def _make_seo(platform):
    return SEOResult(
        content_id=f"seo_{platform}",
        platform=platform,
        title_final=f"{platform} SEO 제목",
        optimized_body=f"{platform} SEO 본문",
        seo_score=8.5,
        tags=["AI", "테스트"],
        meta_description="메타 설명" if platform == "tistory" else None,
    )


class TestPipelineWithDB:
    """Pipeline + DB 통합 테스트"""

    @pytest.mark.asyncio
    async def test_run_saves_to_db(self, db, mock_client):
        """run() 후 DB에 Topic + Content 2개 저장 확인"""
        pipe = Pipeline(mock_client, db_manager=db)

        # 에이전트들 mock
        pipe.researcher.research = AsyncMock(
            return_value=ResearchNote(topic_id="x")
        )
        pipe.splitter.split = AsyncMock(
            return_value=SplitOutlines(
                topic_id="x",
                naver=_make_outline(),
                tistory=_make_outline(),
            )
        )
        pipe.writer.write = AsyncMock(side_effect=[
            _make_draft("naver"), _make_draft("tistory"),
        ])
        pipe.editor.edit = AsyncMock(side_effect=[
            _make_edit("naver"), _make_edit("tistory"),
        ])
        pipe.seo.optimize = AsyncMock(side_effect=[
            _make_seo("naver"), _make_seo("tistory"),
        ])

        from agents.quality_checker import QualityReport
        pipe.checker.check = MagicMock(return_value=QualityReport(
            naver_score=8.0, tistory_score=8.0,
            naver_passed=True, tistory_passed=True,
            similarity=0.3, similarity_passed=True,
            all_passed=True, issues=[],
        ))

        result = await pipe.run("테스트 주제")

        # 결과 확인
        assert result.status == "pending_approval"
        assert result.naver_content_id is not None
        assert result.tistory_content_id is not None

        # DB 확인
        repo = ContentRepository(db)
        topic = repo.get_topic(result.topic.topic_id)
        assert topic is not None
        assert topic.status == TopicStatus.REVIEW.value

        contents = repo.get_contents_by_topic(result.topic.topic_id)
        assert len(contents) == 2
        platforms = {c.platform for c in contents}
        assert platforms == {"naver", "tistory"}

    @pytest.mark.asyncio
    async def test_run_without_db(self, mock_client):
        """DB 없이 run()해도 기존처럼 동작"""
        pipe = Pipeline(mock_client)  # db_manager=None

        pipe.researcher.research = AsyncMock(
            return_value=ResearchNote(topic_id="x")
        )
        pipe.splitter.split = AsyncMock(
            return_value=SplitOutlines(
                topic_id="x",
                naver=_make_outline(),
                tistory=_make_outline(),
            )
        )
        pipe.writer.write = AsyncMock(side_effect=[
            _make_draft("naver"), _make_draft("tistory"),
        ])
        pipe.editor.edit = AsyncMock(side_effect=[
            _make_edit("naver"), _make_edit("tistory"),
        ])
        pipe.seo.optimize = AsyncMock(side_effect=[
            _make_seo("naver"), _make_seo("tistory"),
        ])

        from agents.quality_checker import QualityReport
        pipe.checker.check = MagicMock(return_value=QualityReport(
            naver_score=8.0, tistory_score=8.0,
            naver_passed=True, tistory_passed=True,
            similarity=0.3, similarity_passed=True,
            all_passed=True, issues=[],
        ))

        result = await pipe.run("테스트 주제")
        # DB 없으면 기존 status 유지
        assert result.status == "success"
        assert result.naver_content_id is None
        assert result.tistory_content_id is None


class TestPipelinePublish:
    """Pipeline.publish() 테스트"""

    @pytest.mark.asyncio
    async def test_publish_success(self, db, mock_client):
        """승인된 글 발행 성공 흐름"""
        repo = ContentRepository(db)

        # 테스트 데이터 준비
        from agents.data_models import TopicPackage
        pkg = TopicPackage(
            topic_id="pub_test01", title="발행 테스트",
            keywords=["AI"], category="ai_products",
            content_type="news_briefing", source="manual",
            curator_score=8.0,
        )
        repo.save_topic(pkg)
        naver_cid = repo.save_content(
            "pub_test01", "naver",
            _make_edit("naver"), _make_seo("naver"),
            "<h1>네이버 HTML</h1>",
        )
        tistory_cid = repo.save_content(
            "pub_test01", "tistory",
            _make_edit("tistory"), _make_seo("tistory"),
            "# 티스토리 MD",
        )
        repo.update_topic_status("pub_test01", TopicStatus.APPROVED)

        pipe = Pipeline(mock_client, db_manager=db)

        # publisher mock (publish() 내에서 로컬 import하므로 원본 모듈 경로)
        with patch("publishers.naver_publisher.NaverPublisher") as MockNaver, \
             patch("publishers.tistory_publisher.TistoryPublisher") as MockTistory:

            mock_naver_inst = MockNaver.return_value
            mock_naver_inst.publish = AsyncMock(return_value=PublishResult(
                success=True, platform="naver",
                published_url="https://blog.naver.com/test/1",
                post_id="1",
            ))

            mock_tistory_inst = MockTistory.return_value
            mock_tistory_inst.publish = AsyncMock(return_value=PublishResult(
                success=True, platform="tistory",
                published_url="https://test.tistory.com/1",
                post_id="1",
            ))

            result = await pipe.publish("pub_test01")

        assert result.status == "published"
        assert result.naver_publish_result.success is True
        assert result.tistory_publish_result.success is True

        # DB 상태 확인
        topic = repo.get_topic("pub_test01")
        assert topic.status == TopicStatus.PUBLISHED.value

        contents = repo.get_contents_by_topic("pub_test01")
        for c in contents:
            assert c.published_url is not None
            assert c.status == "published"

    @pytest.mark.asyncio
    async def test_publish_without_db_raises(self, mock_client):
        """DB 없이 publish()하면 RuntimeError"""
        pipe = Pipeline(mock_client)
        with pytest.raises(RuntimeError, match="db_manager가 필요"):
            await pipe.publish("any_id")

    @pytest.mark.asyncio
    async def test_publish_missing_content_raises(self, db, mock_client):
        """콘텐츠가 없으면 ValueError"""
        repo = ContentRepository(db)
        pkg = TopicPackage(
            topic_id="empty01", title="빈 주제",
            keywords=[], category="ai", content_type="news",
            source="manual", curator_score=5.0,
        )
        repo.save_topic(pkg)

        pipe = Pipeline(mock_client, db_manager=db)
        with pytest.raises(ValueError, match="콘텐츠를 찾을 수 없습니다"):
            await pipe.publish("empty01")
