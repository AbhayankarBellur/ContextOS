"""
ContextOS schema.py — Single source of truth for all data models.
All Pydantic v2 models. Kiro generates against these definitions verbatim.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    architecture = "architecture"
    adr = "adr"
    domain = "domain"
    workflow = "workflow"
    product = "product"
    context = "context"
    note = "note"


class DocumentStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    deprecated = "deprecated"


class EdgeType(str, Enum):
    depends_on = "depends_on"
    references = "references"
    implements = "implements"
    relates_to = "relates_to"
    contains = "contains"
    supersedes = "supersedes"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Document(BaseModel):
    id: str                          # sha256 of relative filepath
    project: str                     # from frontmatter
    type: DocumentType               # enum
    domain: Optional[str] = None     # e.g. booking, payment, auth
    status: DocumentStatus = DocumentStatus.draft
    owner: Optional[str] = None
    updated_at: Optional[date] = None
    tags: list[str] = Field(default_factory=list)
    title: str                       # first H1 heading or filename
    filepath: Path                   # absolute path on disk
    content: str                     # full raw markdown


class Chunk(BaseModel):
    id: str                          # sha256 of doc_id + section heading
    doc_id: str                      # parent Document.id
    heading: str                     # the section heading this chunk belongs to
    content: str                     # chunk text
    embedding: list[float] = Field(default_factory=list)  # 384-dim vector
    token_count: int = 0


class GraphNode(BaseModel):
    id: str                          # same as Document.id
    type: DocumentType
    title: str
    domain: Optional[str] = None


class GraphEdge(BaseModel):
    source: str                      # GraphNode.id
    target: str                      # GraphNode.id
    relation: EdgeType


class Token(BaseModel):
    id: str                          # ctx_<random 32 hex chars>
    name: str                        # human label
    hash: str                        # SHA-256 of raw token
    created_at: datetime
    last_used: Optional[datetime] = None
    revoked: bool = False


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    project: str
    type: Optional[DocumentType] = None
    domain: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=20)
    include_graph: bool = False


class SearchResultItem(BaseModel):
    doc_id: str
    title: str
    filepath: str
    type: DocumentType
    domain: Optional[str] = None
    score: float
    chunk: str
    graph_neighbours: list[GraphNode] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    latency_ms: int


class ContextRequest(BaseModel):
    query: str
    project: str
    max_tokens: int = 4000
    priority_order: list[str] = Field(
        default_factory=lambda: [
            "context", "decisions", "architecture", "domain", "workflows", "product"
        ]
    )


class ContextResponse(BaseModel):
    context: str
    sources: list[dict]
    token_estimate: int


class HealthResponse(BaseModel):
    status: str
    indexed: int
    version: str
