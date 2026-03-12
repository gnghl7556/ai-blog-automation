"""
데이터베이스 모델
SQLAlchemy ORM 기반. 주제, 콘텐츠, 성과, 승인 로그 등.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text,
    DateTime, Boolean, JSON, ForeignKey, Enum
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import enum


class Base(DeclarativeBase):
    pass


# ── Enum 정의 ──

class TopicStatus(str, enum.Enum):
    COLLECTED = "collected"         # 수집됨
    QUEUED = "queued"               # 큐에 등록
    RESEARCHING = "researching"     # 리서치 중
    WRITING = "writing"             # 작성 중
    EDITING = "editing"             # 편집 중
    REVIEW = "review"               # 승인 대기
    APPROVED = "approved"           # 승인됨
    PUBLISHED = "published"         # 발행됨
    REJECTED = "rejected"           # 반려됨
    ON_HOLD = "on_hold"             # 보류
    SKIPPED = "skipped"             # 품질 미달 스킵

class ContentType(str, enum.Enum):
    NEWS_BRIEFING = "news_briefing"
    TOOL_REVIEW = "tool_review"
    COMPARISON = "comparison"
    TECH_EXPLAINER = "tech_explainer"
    TREND_ANALYSIS = "trend_analysis"

class Platform(str, enum.Enum):
    NAVER = "naver"
    TISTORY = "tistory"

class ApprovalAction(str, enum.Enum):
    APPROVED = "approved"
    REVISED = "revised"
    REJECTED = "rejected"


# ── 모델 정의 ──

class Topic(Base):
    """수집된 주제"""
    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    title_ko = Column(String)                  # 한국어 번역 제목
    keywords = Column(JSON, default=list)       # ["Claude", "AI에이전트"]
    category = Column(String)                   # 대분류 (ai_products, ai_technology, ai_practical)
    sub_category = Column(String)               # 중분류
    content_type = Column(String)               # 글 유형 (news_briefing, tool_review 등)
    source = Column(String)                     # 소스명 (예: "The Verge")
    source_type = Column(String)                # 소스 유형 (blog, media, community, trend)
    source_url = Column(String)
    language = Column(String, default="en")
    curator_score = Column(Float)               # 주제 선정 점수
    status = Column(String, default=TopicStatus.COLLECTED)
    scheduled_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    contents = relationship("Content", back_populates="topic")
    research_note = relationship("ResearchNote", back_populates="topic", uselist=False)


class ResearchNote(Base):
    """리서치 노트"""
    __tablename__ = "research_notes"

    id = Column(String, primary_key=True)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=False)
    key_facts = Column(JSON, default=list)
    statistics = Column(JSON, default=list)
    analogies = Column(JSON, default=list)       # 비유 소재
    naver_angles = Column(JSON, default=list)    # 네이버용 관점 포인트
    tistory_angles = Column(JSON, default=list)  # 티스토리용 관점 포인트
    sources = Column(JSON, default=list)         # 참고 자료 URL
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="research_note")


class Content(Base):
    """생성된 콘텐츠"""
    __tablename__ = "contents"

    id = Column(String, primary_key=True)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=False)
    platform = Column(String, nullable=False)    # naver / tistory
    title = Column(String)
    body = Column(Text)                          # HTML(네이버) 또는 Markdown(티스토리)
    word_count = Column(Integer)
    quality_score = Column(Float)
    quality_detail = Column(JSON)                # 항목별 점수
    seo_score = Column(Float)
    seo_detail = Column(JSON)
    thumbnail_path = Column(String)
    version = Column(Integer, default=1)
    edit_history = Column(JSON, default=list)
    status = Column(String, default="draft")
    published_url = Column(String)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    topic = relationship("Topic", back_populates="contents")
    performance = relationship("Performance", back_populates="content")
    approval_logs = relationship("ApprovalLog", back_populates="content")


class Performance(Base):
    """콘텐츠 성과 데이터"""
    __tablename__ = "performance"

    id = Column(String, primary_key=True)
    content_id = Column(String, ForeignKey("contents.id"), nullable=False)
    platform = Column(String, nullable=False)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    avg_read_time = Column(Float)                # 평균 체류 시간 (초)
    search_keywords = Column(JSON, default=list) # 유입 키워드
    recorded_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="performance")


class ApprovalLog(Base):
    """승인/수정/반려 로그"""
    __tablename__ = "approval_logs"

    id = Column(String, primary_key=True)
    content_id = Column(String, ForeignKey("contents.id"), nullable=False)
    action = Column(String, nullable=False)      # approved / revised / rejected
    revision_notes = Column(Text)
    rejection_reason = Column(Text)
    responded_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="approval_logs")


class RawTopic(Base):
    """수집된 원시 주제 (Phase 4)"""
    __tablename__ = "raw_topics"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    title_ko = Column(String)
    url = Column(String, unique=True)
    source = Column(String)
    source_type = Column(String)
    summary = Column(Text)
    summary_ko = Column(Text)
    language = Column(String, default="en")
    published_at = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)
    curator_score = Column(Float)
    curator_reason = Column(Text)
    curator_detail = Column(JSON)
    recommended_type = Column(String)
    recommended_category = Column(String)
    status = Column(String, default="collected")
    used_topic_id = Column(String, ForeignKey("topics.id"))


class CostLog(Base):
    """API 비용 로그"""
    __tablename__ = "cost_logs"

    id = Column(String, primary_key=True)
    caller = Column(String)                      # 에이전트명
    model = Column(String)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    elapsed_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── DB 초기화 함수 ──

def init_db(database_url: str = "sqlite:///data/blog.db"):
    """데이터베이스 테이블 생성"""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine

def get_session(engine) -> Session:
    """동기 세션 생성"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
