from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TopicStatus(str, Enum):
    new = "new"
    analyzed = "analyzed"
    drafted = "drafted"
    discarded = "discarded"


class DraftStatus(str, Enum):
    generated = "generated"
    scored = "scored"
    selected = "selected"
    image_ready = "image_ready"
    pending_approval = "pending_approval"
    approved = "approved"
    published = "published"
    rejected = "rejected"
    failed = "failed"


class Topic(BaseModel):
    id: Optional[int] = None
    source: str
    external_id: str
    title: str
    url: Optional[str] = None
    summary: Optional[str] = None
    raw_score: float = 0.0
    fetched_at: str
    status: TopicStatus = TopicStatus.new


class Angle(BaseModel):
    id: Optional[int] = None
    run_id: str
    title: str
    rationale: str
    priority: int
    topic_ids: str  # JSON array of topics.id
    created_at: str


class Draft(BaseModel):
    id: Optional[int] = None
    run_id: str
    angle_id: int
    title: str
    slug: str
    markdown: str
    status: DraftStatus = DraftStatus.generated
    panel_score: Optional[float] = None
    image_path: Optional[str] = None
    image_prompt: Optional[str] = None
    wp_post_id: Optional[int] = None
    wp_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class PanelVote(BaseModel):
    id: Optional[int] = None
    draft_id: int
    persona: str
    score: float
    critique: str
    created_at: str


class Run(BaseModel):
    id: str
    started_at: str
    finished_at: Optional[str] = None
    stage_reached: Optional[str] = None
    notes: Optional[str] = None
