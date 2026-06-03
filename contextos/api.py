"""
ContextOS api.py — FastAPI server.
Binds EXCLUSIVELY to 127.0.0.1 — never 0.0.0.0.
All endpoints (except /health) require Authorization: Bearer ctx_<token>
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from contextos.schema import (
    SearchRequest, SearchResponse, ContextRequest, ContextResponse,
    HealthResponse, DocumentType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory — lazy-init heavy objects on first request
# ---------------------------------------------------------------------------

_embedder = None
_store = None
_graph_builder = None
_config = None


def get_config():
    global _config
    if _config is None:
        from contextos.config import load_config
        _config = load_config()
    return _config


def get_embedder():
    global _embedder
    if _embedder is None:
        from contextos.embedder import Embedder
        cfg = get_config()
        _embedder = Embedder(cfg.embeddings_dir)
    return _embedder


def get_store():
    global _store
    if _store is None:
        from contextos.store import VectorStore
        cfg = get_config()
        _store = VectorStore(cfg.lancedb_dir)
    return _store


def get_graph():
    global _graph_builder
    if _graph_builder is None:
        from contextos.graph import GraphBuilder
        cfg = get_config()
        _graph_builder = GraphBuilder()
        _graph_builder.load(cfg.graph_dir)
    return _graph_builder


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ContextOS",
    description="Local-first knowledge OS for AI coding agents",
    version="1.0.0-rc1",
    docs_url="/docs",
    redoc_url=None,
)

# Only allow localhost origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


def require_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Validate Bearer token. Raises 401 if missing or invalid."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header required")

    from contextos.auth import validate_token
    cfg = get_config()
    token = validate_token(credentials.credentials, cfg.tokens_dir)

    if token is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")

    return token


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    """Health check — no auth required. Used by agents to verify server is running."""
    store = get_store()
    doc_count = store.count_documents()
    return HealthResponse(
        status="ok",
        indexed=doc_count,
        version="1.0.0-rc1",
    )


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    session_id: Optional[str] = None,
    _token=Depends(require_token),
):
    """Primary retrieval endpoint. Agents call this to find relevant document chunks."""
    from contextos.retrieval import search as do_search

    embedder = get_embedder()
    store    = get_store()
    graph    = get_graph() if request.include_graph else None

    result = do_search(
        query=request.query,
        embedder=embedder,
        store=store,
        graph_builder=graph,
        project=request.project or None,
        type_filter=request.type.value if request.type else None,
        domain_filter=request.domain,
        limit=request.limit,
        include_graph=request.include_graph,
    )

    # Log to session if provided
    if session_id:
        try:
            from contextos.session import log_search
            cfg = get_config()
            log_search(cfg.contextos_dir / "sessions", session_id,
                       request.query, len(result.results))
        except Exception:
            pass

    return result


@app.post("/context", response_model=ContextResponse)
def context(
    request: ContextRequest,
    session_id: Optional[str] = None,
    _token=Depends(require_token),
):
    """Assemble a ready-to-paste context block for an agent task."""
    from contextos.retrieval import assemble_context

    embedder = get_embedder()
    store    = get_store()
    graph    = get_graph()

    result = assemble_context(
        query=request.query,
        embedder=embedder,
        store=store,
        graph_builder=graph,
        project=request.project or None,
        max_tokens=request.max_tokens,
        priority_order=request.priority_order,
    )

    # Log to session if provided
    if session_id:
        try:
            from contextos.session import log_context
            cfg = get_config()
            log_context(cfg.contextos_dir / "sessions", session_id,
                        request.query, result.token_estimate)
        except Exception:
            pass

    return result


@app.get("/graph")
def graph_endpoint(_token=Depends(require_token)):
    """Return the full knowledge graph as nodes and edges."""
    graph_builder = get_graph()
    cfg = get_config()

    graph_path = cfg.graph_dir / "graph.json"
    if not graph_path.exists():
        return {"nodes": [], "edges": [], "summary": {"nodes": 0, "edges": 0}}

    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = graph_builder.get_summary()
    data["summary"] = summary
    return data


@app.get("/documents")
def list_documents(
    project: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    _token=Depends(require_token),
):
    """List all indexed documents with optional filters."""
    store = get_store()
    docs = store.list_documents(
        project=project,
        type_filter=type,
        domain_filter=domain,
        status_filter=status,
    )
    return {"documents": docs, "count": len(docs)}


# ---------------------------------------------------------------------------
# Watcher status
# ---------------------------------------------------------------------------

@app.get("/watcher")
def watcher_status_endpoint(_token=Depends(require_token)):
    """Return live watch mode status."""
    try:
        from contextos.watcher import watcher_status
        return watcher_status()
    except Exception:
        return {"active": False}


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@app.post("/session/start")
def session_start_ep(
    name: Optional[str] = None,
    _token=Depends(require_token),
):
    """Start a new agent session."""
    from contextos.session import create_session
    cfg = get_config()
    session = create_session(cfg.contextos_dir / "sessions", name)
    return {"session_id": session["id"], "name": session["name"], "started_at": session["started_at"]}


@app.post("/session/{session_id}/event")
def session_event_ep(
    session_id: str,
    event_type: str,
    payload: dict,
    _token=Depends(require_token),
):
    """Log an event to an active session."""
    from contextos.session import add_event
    cfg = get_config()
    success = add_event(cfg.contextos_dir / "sessions", session_id, event_type, payload)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found or ended")
    return {"ok": True}


@app.post("/session/{session_id}/end")
def session_end_ep(session_id: str, _token=Depends(require_token)):
    """End a session and generate summary."""
    from contextos.session import end_session
    cfg = get_config()
    try:
        session = end_session(cfg.contextos_dir / "sessions", session_id)
        return {"session_id": session_id, "summary": session.get("summary", {})}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/session/last")
def session_last_ep(_token=Depends(require_token)):
    """Return the most recent completed session summary."""
    from contextos.session import get_last_session
    cfg = get_config()
    session = get_last_session(cfg.contextos_dir / "sessions")
    return {"session": session}


@app.get("/session/active")
def session_active_ep(_token=Depends(require_token)):
    """Return the currently active session, if any."""
    from contextos.session import get_active_session
    cfg = get_config()
    return {"session": get_active_session(cfg.contextos_dir / "sessions")}


# ---------------------------------------------------------------------------
# Pull endpoint
# ---------------------------------------------------------------------------

@app.post("/pull")
def pull_ep(
    connector: str,
    source: Optional[str] = None,
    project: Optional[str] = None,
    pull_type: Optional[str] = None,
    force: bool = False,
    _token=Depends(require_token),
):
    """Pull external data from a connector into the output directory."""
    from contextos.connectors import CONNECTORS
    cfg = get_config()
    conn_cls = CONNECTORS.get(connector.lower())
    if not conn_cls:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")
    proj = project or cfg.project_name
    conn_config: dict = {}
    if source:    conn_config["source"] = source; conn_config["repo"] = source
    if pull_type: conn_config["type"]   = pull_type
    conn    = conn_cls(project=proj, config=conn_config)
    out_dir = cfg.contextos_dir / "pulled" / connector / proj
    try:
        return conn.pull(out_dir, force=force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Return the FastAPI app instance."""
    return app


def run_server(port: int = 8080):
    """
    Start uvicorn server. ALWAYS binds to 127.0.0.1.
    Never binds to 0.0.0.0 — this is enforced here and not configurable.
    """
    import uvicorn

    logger.info("Starting ContextOS API on http://127.0.0.1:%d", port)
    uvicorn.run(
        "contextos.api:app",
        host="127.0.0.1",   # HARDCODED — never 0.0.0.0
        port=port,
        log_level="warning",
        reload=False,
    )
