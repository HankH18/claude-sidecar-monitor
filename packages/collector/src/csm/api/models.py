"""Pydantic shapes mirrored by packages/dashboard/src/api/types.ts.

Keep both files in sync — the dashboard types intentionally match these
field names.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SessionState = Literal["idle", "running", "tool", "hung", "done", "waiting_user"]


class Session(BaseModel):
    session_id: str
    parent_session_id: str | None = None
    worktree_root: str
    project_label: str | None = None
    cwd: str
    transcript_path: str | None = None
    agent_type: str | None = None
    state: SessionState
    last_event_at: str
    last_event_name: str | None = None
    last_tool_name: str | None = None
    started_at: str
    completed_at: str | None = None
    primary_model: str | None = None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


class ModelTokens(BaseModel):
    model: str
    input: int
    output: int
    cache_read: int
    cache_write: int


class SubtreeTokens(BaseModel):
    input: int
    output: int
    cache_read: int
    cache_write: int
    descendant_count: int


class SessionDetail(Session):
    by_model: list[ModelTokens] = Field(default_factory=list)


class TranscriptMessage(BaseModel):
    message_id: int
    session_id: str
    role: str
    timestamp: str
    content_json: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class TranscriptPage(BaseModel):
    messages: list[TranscriptMessage]
    next_cursor: int | None = None  # message_id after which to continue


class TreeNode(BaseModel):
    session: Session
    children: list[TreeNode] = Field(default_factory=list)
    subtree_tokens: SubtreeTokens


class StateSnapshot(BaseModel):
    sessions: list[Session]
    settings: dict[str, str]
    last_event_at: str | None = None


class TopSession(BaseModel):
    session_id: str
    project_label: str | None = None
    worktree_root: str
    agent_type: str | None = None
    primary_model: str | None = None
    started_at: str
    input: int
    output: int
    cache_read: int
    cache_write: int


class TopProject(BaseModel):
    worktree_root: str
    project_label: str | None = None
    session_count: int
    input: int
    output: int
    cache_read: int
    cache_write: int


class DailyTotal(BaseModel):
    date: str
    model: str
    input: int
    output: int
    cache_read: int
    cache_write: int


class TokensResponse(BaseModel):
    topSessions: list[TopSession]
    topProjects: list[TopProject]
    totalsByModel: list[ModelTokens]
    dailyTotals: list[DailyTotal]


class Settings(BaseModel):
    hang_yellow_ms: int
    hang_red_ms: int
    ntfy_topic: str


class SettingsPatch(BaseModel):
    hang_yellow_ms: int | None = None
    hang_red_ms: int | None = None
    ntfy_topic: str | None = None


class ApiError(BaseModel):
    code: str
    message: str


class ApiErrorWrapper(BaseModel):
    error: ApiError
