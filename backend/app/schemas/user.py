from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreateRequest(BaseModel):
    external_user_id: str
    name: str | None = None
    timezone: str = "Asia/Shanghai"


class UserResponse(BaseModel):
    id: str
    external_user_id: str
    name: str | None = None
    timezone: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdateRequest(BaseModel):
    profile: dict = Field(default_factory=dict)
    goals: dict = Field(default_factory=dict)
    thresholds: dict = Field(default_factory=dict)
    baseline_stats: dict = Field(default_factory=dict)
    system_prompt_prefix: str = ""


class ProfileResponse(BaseModel):
    id: str
    user_id: str
    profile_json: dict
    goals_json: dict
    thresholds_json: dict
    baseline_stats_json: dict
    system_prompt_prefix: str
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserListItem(BaseModel):
    id: str
    external_user_id: str
    name: str | None = None
    timezone: str
    created_at: datetime
    segment_count: int
    last_segment_at: datetime | None = None


class UsersListResponse(BaseModel):
    items: list[UserListItem]
    total: int
    limit: int
    offset: int


class TimelineItem(BaseModel):
    segment_id: str
    segment_start: datetime
    segment_end: datetime
    granularity: str
    top_label: str | None = None
    probabilities: dict | None = None


class TimelineResponse(BaseModel):
    user_id: str
    items: list[TimelineItem]
