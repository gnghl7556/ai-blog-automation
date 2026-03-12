"""
Pydantic 데이터 모델 — 에이전트 간 데이터 전달용
각 에이전트의 입출력 형식을 정의합니다.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 주제 관련 ──

class TopicPackage(BaseModel):
    """주제 선정 에이전트 출력"""
    topic_id: str
    title: str
    title_ko: Optional[str] = None
    keywords: list[str] = []
    category: str
    sub_category: Optional[str] = None
    content_type: str
    source: str
    source_url: Optional[str] = None
    curator_score: float


# ── 리서치 관련 ──

class ResearchNote(BaseModel):
    """리서치 에이전트 출력"""
    topic_id: str
    key_facts: list[dict] = []        # [{"fact": "...", "source": "...", "reliability": "high"}]
    statistics: list[dict] = []       # [{"stat": "...", "source": "..."}]
    analogies: list[str] = []         # 비유 소재
    naver_angles: list[str] = []      # 네이버용 관점
    tistory_angles: list[str] = []    # 티스토리용 관점
    sources: list[str] = []           # 참고 URL


# ── 관점 분화 ──

class SectionOutline(BaseModel):
    """섹션 아웃라인"""
    title: str
    key_points: list[str]
    references: list[str] = []

class PlatformOutline(BaseModel):
    """플랫폼별 아웃라인"""
    title_candidates: list[str]
    sections: list[SectionOutline]
    target_length: tuple[int, int]     # (최소, 최대) 자 수
    tone_notes: Optional[str] = None

class SplitOutlines(BaseModel):
    """관점 분화 에이전트 출력"""
    topic_id: str
    naver: PlatformOutline
    tistory: PlatformOutline


# ── 글 작성 ──

class PlatformDraft(BaseModel):
    """작성 에이전트 출력"""
    content_id: str
    topic_id: str
    platform: str                      # "naver" or "tistory"
    title: str
    body: str
    word_count: int
    image_placeholders: list[dict] = []  # [{"position": "섹션2 뒤", "description": "..."}]


# ── 편집 ──

class EditResult(BaseModel):
    """편집 에이전트 출력"""
    content_id: str
    platform: str
    final_draft: str
    quality_score: float
    quality_detail: dict               # {"accuracy": X, "readability": X, ...}
    edit_summary: dict                 # {"factcheck": "...", "readability_edits": "...", ...}
    passed: bool                       # 품질 기준 통과 여부


# ── SEO ──

class SEOResult(BaseModel):
    """SEO 에이전트 출력"""
    content_id: str
    platform: str
    title_final: str
    optimized_body: str
    seo_score: float
    tags: list[str] = []
    meta_description: Optional[str] = None   # 티스토리 전용
    schema_markup: Optional[dict] = None     # 티스토리 전용


# ── 썸네일 ──

class ThumbnailResult(BaseModel):
    """썸네일 에이전트 출력"""
    topic_id: str
    naver_path: str
    tistory_path: str


# ── 최종 콘텐츠 패키지 (승인 게이트 전달용) ──

class ContentPackage(BaseModel):
    """승인 게이트에 전달하는 최종 패키지"""
    topic_id: str
    topic_title: str
    content_type: str
    category: str

    naver_content_id: str
    naver_title: str
    naver_body: str
    naver_quality_score: float
    naver_seo_score: float
    naver_tags: list[str]
    naver_thumbnail_path: str

    tistory_content_id: str
    tistory_title: str
    tistory_body: str
    tistory_quality_score: float
    tistory_seo_score: float
    tistory_tags: list[str]
    tistory_meta_description: Optional[str]
    tistory_thumbnail_path: str

    scheduled_time: Optional[str] = None
    keywords: list[str] = []

    # 미리보기 이미지 경로 (Playwright 스크린샷)
    naver_preview_path: Optional[str] = None
    tistory_preview_path: Optional[str] = None


# ── 발행 결과 ──

class PublishResult(BaseModel):
    """플랫폼 발행 결과 (네이버/티스토리 공통)"""
    success: bool
    platform: str
    published_url: Optional[str] = None
    post_id: Optional[str] = None
    error: Optional[str] = None
