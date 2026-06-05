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


class TokenScope(str, Enum):
    """Token permission scopes.
    read  — search, context, documents, graph (agents, CI read)
    write — index, pull, import, session write (trusted agents)
    admin — token management, audit, memory reset (operators only)
    """
    read  = "read"
    write = "write"
    admin = "admin"

    @classmethod
    def allows(cls, token_scope: "TokenScope", required: "TokenScope") -> bool:
        """Check if token_scope satisfies required scope (admin > write > read)."""
        order = {cls.read: 0, cls.write: 1, cls.admin: 2}
        return order.get(token_scope, -1) >= order.get(required, 0)


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
    id: str
    name: str
    hash: str
    created_at: datetime
    last_used: Optional[datetime] = None
    revoked: bool = False
    scope: Optional[TokenScope] = TokenScope.write
    expires_at: Optional[datetime] = None
    request_count: int = 0

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at

    def has_scope(self, required: TokenScope) -> bool:
        if self.scope is None:
            return True  # legacy tokens without scope: full access
        return TokenScope.allows(self.scope, required)


class AuditEntry(BaseModel):
    request_id: str
    token_id: str
    token_name: str
    endpoint: str
    method: str
    latency_ms: int
    scope: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    project: Optional[str] = None
    type: Optional[DocumentType] = None
    domain: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=20)
    include_graph: bool = False
    use_hybrid: bool = True
    hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0)


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
    project: Optional[str] = None
    max_tokens: int = 4000
    priority_order: list[str] = Field(
        default_factory=lambda: [
            "context", "decisions", "architecture", "domain", "workflows", "product"
        ]
    )
    use_hybrid: bool = True
    hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0)


class ContextResponse(BaseModel):
    context: str
    sources: list[dict]
    token_estimate: int


class HealthResponse(BaseModel):
    status: str
    indexed: int
    version: str
