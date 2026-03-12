"""
DatabaseManager 테스트 — SQLite :memory: 사용
"""

import pytest

from database.models import Base, Topic, TopicStatus


class TestDatabaseManager:
    """DatabaseManager 기본 동작 검증"""

    def test_create_tables(self, db):
        """테이블 생성 확인"""
        tables = Base.metadata.tables.keys()
        assert "topics" in tables
        assert "contents" in tables
        assert "approval_logs" in tables

    def test_get_session_commit(self, db):
        """세션 자동 커밋 확인"""
        with db.get_session() as session:
            topic = Topic(
                id="test001",
                title="테스트 주제",
                status=TopicStatus.COLLECTED.value,
            )
            session.add(topic)

        # 새 세션에서 조회 가능해야 함
        with db.get_session() as session:
            found = session.query(Topic).filter_by(id="test001").first()
            assert found is not None
            assert found.title == "테스트 주제"

    def test_get_session_rollback(self, db):
        """예외 시 자동 롤백 확인"""
        with pytest.raises(ValueError):
            with db.get_session() as session:
                session.add(Topic(id="rollback01", title="롤백 테스트"))
                raise ValueError("강제 예외")

        with db.get_session() as session:
            found = session.query(Topic).filter_by(id="rollback01").first()
            assert found is None

    def test_multiple_sessions(self, db):
        """여러 세션 독립 동작 확인"""
        with db.get_session() as s1:
            s1.add(Topic(id="multi01", title="세션1"))

        with db.get_session() as s2:
            s2.add(Topic(id="multi02", title="세션2"))

        with db.get_session() as s3:
            count = s3.query(Topic).count()
            assert count == 2
