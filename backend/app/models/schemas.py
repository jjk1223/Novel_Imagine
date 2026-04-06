from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NovelRequest(BaseModel):
    """User input to kick off novel generation."""
    premise: str = Field(..., min_length=1, description="用户的初始构想/大纲")
    genre: str = Field(default="奇幻", description="题材类型")
    num_chapters: int = Field(default=5, ge=1, le=50, description="目标章节数")
    provider: Literal["ollama", "qwen"] = "ollama"


class CharacterProfile(BaseModel):
    name: str
    role: str
    description: str


class ChapterOutline(BaseModel):
    chapter_number: int
    title: str
    brief: str


class OutlineResult(BaseModel):
    title: str
    world_building: str = ""
    main_characters: list[CharacterProfile] = Field(default_factory=list)
    character_relationships: str = ""
    writing_style: str = ""
    outline: str = ""
    chapters: list[ChapterOutline]


class GenerateFromOutlineRequest(BaseModel):
    """Start writing from a confirmed (possibly user-edited) outline."""
    novel_id: int
    outline: OutlineResult
    provider: Literal["ollama", "qwen"] = "ollama"


class ResumeRequest(BaseModel):
    """Resume writing a novel from where it left off."""
    novel_id: int
    provider: Literal["ollama", "qwen"] = "ollama"


class GraphNode(BaseModel):
    id: str
    label: str
    properties: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    properties: dict = Field(default_factory=dict)


class GraphUpdate(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class SSEEvent(BaseModel):
    """Unified SSE payload pushed to the frontend."""
    event: Literal["status", "text", "outline", "graph", "thinking", "error", "done"]
    data: str | dict | list = ""


class ChapterOut(BaseModel):
    id: int
    chapter_number: int
    title: str
    summary: str
    content: str
    status: str

    class Config:
        from_attributes = True


class NovelOut(BaseModel):
    id: int
    title: str
    premise: str
    outline: str
    status: str
    created_at: datetime
    chapters: list[ChapterOut] = []

    class Config:
        from_attributes = True


class NovelListItem(BaseModel):
    id: int
    title: str
    premise: str
    status: str
    created_at: datetime
    chapter_count: int = 0

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    sqlite: str
    neo4j: str
    llm: str
