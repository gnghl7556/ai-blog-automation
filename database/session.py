"""
DatabaseManager — DB 세션 관리
동기 SQLAlchemy 세션의 생성·커밋·롤백을 자동 처리합니다.
"""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base

DEFAULT_DATABASE_URL = "sqlite:///data/blog.db"


class DatabaseManager:
    """데이터베이스 연결·세션 관리

    Args:
        database_url: SQLAlchemy 연결 문자열.
            기본값은 ``sqlite:///data/blog.db``.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or DEFAULT_DATABASE_URL
        self.engine = create_engine(self.database_url, echo=False)
        self._session_factory = sessionmaker(bind=self.engine)

    def create_tables(self) -> None:
        """모든 테이블 생성 (없으면 CREATE, 있으면 무시)"""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """자동 commit/rollback 세션 컨텍스트 매니저

        Yields:
            SQLAlchemy Session
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
