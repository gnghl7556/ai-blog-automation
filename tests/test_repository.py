"""
ContentRepository 테스트 — CRUD 검증
"""

import pytest

from database.repository import ContentRepository
from database.models import TopicStatus
from agents.data_models import TopicPackage, EditResult, SEOResult


@pytest.fixture
def repo(db):
    """ContentRepository"""
    return ContentRepository(db)


@pytest.fixture
def sample_topic_pkg():
    """샘플 TopicPackage"""
    return TopicPackage(
        topic_id="tp_test001",
        title="Claude 4 출시 소식",
        keywords=["Claude", "AI", "Anthropic"],
        category="ai_products",
        content_type="news_briefing",
        source="manual_input",
        curator_score=8.5,
    )


@pytest.fixture
def sample_edit_result():
    """샘플 EditResult"""
    return EditResult(
        content_id="edit01",
        platform="naver",
        final_draft="편집된 본문입니다.",
        quality_score=7.8,
        quality_detail={"accuracy": 8.0, "readability": 7.5},
        edit_summary={"factcheck": "OK"},
        passed=True,
    )


@pytest.fixture
def sample_seo_result():
    """샘플 SEOResult"""
    return SEOResult(
        content_id="seo01",
        platform="naver",
        title_final="Claude 4, AI의 새로운 시대를 열다",
        optimized_body="SEO 최적화된 본문",
        seo_score=8.2,
        tags=["Claude", "AI", "Anthropic"],
        meta_description="Claude 4 출시 요약",
    )


class TestSaveTopic:
    """save_topic 테스트"""

    def test_save_and_retrieve(self, repo, sample_topic_pkg):
        topic_id = repo.save_topic(sample_topic_pkg)
        assert topic_id == "tp_test001"

        topic = repo.get_topic(topic_id)
        assert topic is not None
        assert topic.title == "Claude 4 출시 소식"
        assert topic.category == "ai_products"
        assert topic.status == TopicStatus.WRITING.value

    def test_save_sets_writing_status(self, repo, sample_topic_pkg):
        repo.save_topic(sample_topic_pkg)
        topic = repo.get_topic("tp_test001")
        assert topic.status == TopicStatus.WRITING.value


class TestUpdateTopicStatus:
    """update_topic_status 테스트"""

    def test_update_status(self, repo, sample_topic_pkg):
        repo.save_topic(sample_topic_pkg)
        repo.update_topic_status("tp_test001", TopicStatus.REVIEW)

        topic = repo.get_topic("tp_test001")
        assert topic.status == TopicStatus.REVIEW.value

    def test_update_nonexistent_topic(self, repo):
        """존재하지 않는 주제 업데이트는 에러 없이 무시"""
        repo.update_topic_status("nonexistent", TopicStatus.APPROVED)


class TestSaveContent:
    """save_content 테스트"""

    def test_save_and_retrieve(
        self, repo, sample_topic_pkg, sample_edit_result, sample_seo_result,
    ):
        repo.save_topic(sample_topic_pkg)
        content_id = repo.save_content(
            topic_id="tp_test001",
            platform="naver",
            edit_result=sample_edit_result,
            seo_result=sample_seo_result,
            body_final="<h1>최종 HTML</h1>",
        )

        assert content_id is not None
        assert len(content_id) == 12

        contents = repo.get_contents_by_topic("tp_test001")
        assert len(contents) == 1
        assert contents[0].platform == "naver"
        assert contents[0].title == "Claude 4, AI의 새로운 시대를 열다"
        assert contents[0].body == "<h1>최종 HTML</h1>"
        assert contents[0].quality_score == 7.8
        assert contents[0].seo_score == 8.2

    def test_save_two_platforms(
        self, repo, sample_topic_pkg, sample_edit_result, sample_seo_result,
    ):
        repo.save_topic(sample_topic_pkg)

        # 네이버
        repo.save_content(
            "tp_test001", "naver",
            sample_edit_result, sample_seo_result, "<h1>네이버</h1>",
        )
        # 티스토리
        tistory_edit = EditResult(
            content_id="edit02", platform="tistory",
            final_draft="티스토리 본문", quality_score=7.5,
            quality_detail={}, edit_summary={}, passed=True,
        )
        tistory_seo = SEOResult(
            content_id="seo02", platform="tistory",
            title_final="티스토리 제목", optimized_body="티스토리 SEO",
            seo_score=7.9, tags=["AI"],
        )
        repo.save_content(
            "tp_test001", "tistory",
            tistory_edit, tistory_seo, "# 티스토리 마크다운",
        )

        contents = repo.get_contents_by_topic("tp_test001")
        assert len(contents) == 2
        platforms = {c.platform for c in contents}
        assert platforms == {"naver", "tistory"}


class TestUpdateContentPublished:
    """update_content_published 테스트"""

    def test_update_published(
        self, repo, sample_topic_pkg, sample_edit_result, sample_seo_result,
    ):
        repo.save_topic(sample_topic_pkg)
        content_id = repo.save_content(
            "tp_test001", "naver",
            sample_edit_result, sample_seo_result, "본문",
        )

        repo.update_content_published(content_id, "https://blog.naver.com/test/123")

        contents = repo.get_contents_by_topic("tp_test001")
        assert contents[0].published_url == "https://blog.naver.com/test/123"
        assert contents[0].status == "published"
        assert contents[0].published_at is not None


class TestSaveApprovalLog:
    """save_approval_log 테스트"""

    def test_save_approval(
        self, repo, sample_topic_pkg, sample_edit_result, sample_seo_result,
    ):
        repo.save_topic(sample_topic_pkg)
        content_id = repo.save_content(
            "tp_test001", "naver",
            sample_edit_result, sample_seo_result, "본문",
        )

        log_id = repo.save_approval_log(content_id, "approved", notes="CLI 승인")
        assert log_id is not None
        assert len(log_id) == 12


class TestGetTopicsByStatus:
    """get_topics_by_status 테스트"""

    def test_filter_by_status(self, repo):
        pkg1 = TopicPackage(
            topic_id="t1", title="주제1", keywords=[],
            category="ai", content_type="news", source="manual",
            curator_score=5.0,
        )
        pkg2 = TopicPackage(
            topic_id="t2", title="주제2", keywords=[],
            category="ai", content_type="news", source="manual",
            curator_score=5.0,
        )
        repo.save_topic(pkg1)
        repo.save_topic(pkg2)
        repo.update_topic_status("t1", TopicStatus.REVIEW)

        review_topics = repo.get_topics_by_status(TopicStatus.REVIEW.value)
        assert len(review_topics) == 1
        assert review_topics[0].id == "t1"

        writing_topics = repo.get_topics_by_status(TopicStatus.WRITING.value)
        assert len(writing_topics) == 1
        assert writing_topics[0].id == "t2"


class TestGetAllTopics:
    """get_all_topics 테스트"""

    def test_empty(self, repo):
        assert repo.get_all_topics() == []

    def test_returns_all(self, repo):
        for i in range(3):
            pkg = TopicPackage(
                topic_id=f"all_{i}", title=f"주제 {i}", keywords=[],
                category="ai", content_type="news", source="manual",
                curator_score=5.0,
            )
            repo.save_topic(pkg)

        topics = repo.get_all_topics()
        assert len(topics) == 3
