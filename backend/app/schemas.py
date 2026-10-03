from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIResponse(BaseModel):
    success: bool = True
    data: object | None = None
    message: str = "操作成功"
    request_id: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    video_ratio: Literal["9:16"] = "9:16"
    duration_seconds: int = Field(default=5, ge=1, le=60)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["draft", "ready", "generating", "completed", "failed", "archived"] | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: str
    video_ratio: str
    duration_seconds: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    asset_count: int = 0
    job_count: int = 0
    token_usage_status: str = "unavailable"
    token_total: int = 0
    token_input: int = 0
    token_output: int = 0


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    asset_type: str
    original_name: str
    display_name: str
    stored_path: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None
    slot_index: int | None
    created_at: datetime
    file_url: str
    thumbnail_url: str


class AssetUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    slot_index: int | None = Field(default=None, ge=0, le=2)


class ReorderRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=3, max_length=3)


class JobCreate(BaseModel):
    provider: Literal["mock", "agnes"] = "mock"
    video_ratio: Literal["9:16"] = "9:16"
    duration_seconds: int = Field(default=5, ge=1, le=60)
    transition_style: Literal["natural"] = "natural"
    clothing_order: list[str] = Field(min_length=3, max_length=3)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    project_name: str | None = None
    project_deleted: bool = False
    provider: str
    status: str
    progress: int
    current_node: str | None
    provider_job_id: str | None
    workflow_version: str
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    token_usage_status: str = "unavailable"
    token_total: int = 0
    token_input: int = 0
    token_output: int = 0


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    database: str
