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

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path as _Path

from contextos.schema import (
    SearchRequest, SearchResponse, ContextRequest, ContextResponse,
    HealthResponse, DocumentType, TokenScope,
    WriteMemoryRequest, QueryMemoryRequest,
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
    version="2.0.0-rc1",
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


# ---------------------------------------------------------------------------
# Request ID + logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    from contextos.logger import get_logger, new_request_id
    request_id = new_request_id()
    request.state.request_id = request_id
    request.state.start_time = time.time()

    response = await call_next(request)

    latency_ms = int((time.time() - request.state.start_time) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Latency-MS"] = str(latency_ms)

    try:
        cfg    = get_config()
        from contextos.logger import get_logger
        logger = get_logger(cfg.logs_dir)
        logger.log_request(
            request_id  = request_id,
            endpoint    = request.url.path,
            method      = request.method,
            latency_ms  = latency_ms,
            token_id    = None,
            status_code = response.status_code,
        )
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).debug("Request logging failed: %s", exc)

    return response


def require_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Validate Bearer token. Raises 401 if missing/invalid, 403 if expired, 429 if rate limited."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header required")

    from contextos.auth import validate_token, check_rate_limit
    cfg = get_config()
    token = validate_token(credentials.credentials, cfg.tokens_dir)

    if token is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")

    if token.is_expired():
        raise HTTPException(status_code=403, detail="Token has expired")

    if not check_rate_limit(token, cfg.tokens_dir):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded — 1000 req/min",
            headers={"Retry-After": "60"},
        )

    return token


def require_scope(required: TokenScope):
    """Dependency factory: enforce a minimum token scope."""
    def _check(token=Depends(require_token)):
        if not token.has_scope(required):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient scope. Required: {required.value}, "
                       f"token has: {token.scope.value if token.scope else 'none'}"
            )
        return token
    return _check


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=None)
def health(deep: bool = Query(False, description="Run a live search to verify end-to-end")):
    """Health check. ?deep=true runs a sample search to verify retrieval works."""
    store     = get_store()
    doc_count = store.count_documents()

    if deep:
        # End-to-end verification
        try:
            embedder = get_embedder()
            qv = embedder.embed_query("health check")
            results = store.search(qv, limit=1)
            retrieval_ok = True
        except Exception as exc:
            logger.warning("Deep health check failed: %s", exc)
            retrieval_ok = False

        return {
            "status":       "ok" if retrieval_ok else "degraded",
            "indexed":      doc_count,
            "version":      "2.0.0-rc1",
            "retrieval_ok": retrieval_ok,
        }

    return HealthResponse(status="ok", indexed=doc_count, version="2.0.0-rc1")


@app.get("/metrics")
def metrics(_token=Depends(require_scope(TokenScope.read))):
    """Return request metrics: total_requests, avg_latency_ms, cache stats."""
    from contextos.logger import get_logger
    from contextos.cache_layer import get_cache
    cfg = get_config()
    log_metrics   = get_logger(cfg.logs_dir).get_metrics()
    cache_stats   = get_cache().stats()
    return {**log_metrics, "cache": cache_stats}


@app.get("/audit")
def audit(
    limit: int = Query(50, le=500),
    _token=Depends(require_scope(TokenScope.admin)),
):
    """Return recent audit log entries. Requires admin scope."""
    from contextos.logger import get_logger
    cfg = get_config()
    return {"entries": get_logger(cfg.logs_dir).read_audit(limit=limit)}


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    session_id: Optional[str] = None,
    _token=Depends(require_scope(TokenScope.read)),
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
        use_hybrid=request.use_hybrid,
        hybrid_alpha=request.hybrid_alpha,
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
    _token=Depends(require_scope(TokenScope.read)),
):
    """Assemble a ready-to-paste context block. Cached for 5 minutes per query."""
    from contextos.retrieval import assemble_context
    from contextos.cache_layer import get_cache

    cache = get_cache()
    cache_key = cache.make_key(request.query, request.project, request.max_tokens)

    # Try cache first
    cached = cache.get(cache_key)
    if cached is not None:
        if session_id:
            try:
                from contextos.session import log_context
                cfg = get_config()
                log_context(cfg.contextos_dir / "sessions", session_id,
                            request.query, cached.token_estimate)
            except Exception:
                pass
        return cached

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
        use_hybrid=getattr(request, 'use_hybrid', True),
        hybrid_alpha=getattr(request, 'hybrid_alpha', 0.7),
    )

    # Store in cache
    cache.set(cache_key, result)

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
def graph_endpoint(_token=Depends(require_scope(TokenScope.read))):
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
    _token=Depends(require_scope(TokenScope.read)),
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




@app.get("/dashboard", include_in_schema=False)
def dashboard_ui():
    """Serve the ContextOS web dashboard. No auth required (localhost only)."""
    from fastapi.responses import HTMLResponse as _HR
    static_file = Path(__file__).parent / "static" / "dashboard.html"
    if static_file.exists():
        return _HR(content=static_file.read_text(encoding="utf-8"))
    return _HR(content="<h1>ContextOS Dashboard</h1><p>Static file missing.</p>", status_code=404)

# ---------------------------------------------------------------------------
# Watcher status
# ---------------------------------------------------------------------------

@app.get("/watcher")
def watcher_status_endpoint(_token=Depends(require_scope(TokenScope.read))):
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
    _token=Depends(require_scope(TokenScope.read)),
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
    _token=Depends(require_scope(TokenScope.read)),
):
    """Log an event to an active session."""
    from contextos.session import add_event
    cfg = get_config()
    success = add_event(cfg.contextos_dir / "sessions", session_id, event_type, payload)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found or ended")
    return {"ok": True}


@app.post("/session/{session_id}/end")
def session_end_ep(session_id: str, _token=Depends(require_scope(TokenScope.read))):
    """End a session and generate summary."""
    from contextos.session import end_session
    cfg = get_config()
    try:
        session = end_session(cfg.contextos_dir / "sessions", session_id)
        return {"session_id": session_id, "summary": session.get("summary", {})}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/session/last")
def session_last_ep(_token=Depends(require_scope(TokenScope.read))):
    """Return the most recent completed session summary."""
    from contextos.session import get_last_session
    cfg = get_config()
    session = get_last_session(cfg.contextos_dir / "sessions")
    return {"session": session}


@app.get("/session/active")
def session_active_ep(_token=Depends(require_scope(TokenScope.read))):
    """Return the currently active session, if any."""
    from contextos.session import get_active_session
    cfg = get_config()
    return {"session": get_active_session(cfg.contextos_dir / "sessions")}


# ---------------------------------------------------------------------------
# Pull endpoint
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# User Memory endpoints
# ---------------------------------------------------------------------------

@app.post("/memory/write")
def memory_write(
    request: WriteMemoryRequest,
    _token=Depends(require_scope(TokenScope.write)),
):
    """Write a memory fragment for a user. Cross-app: any client can write."""
    from contextos.user_memory import write_fragment
    cfg = get_config()
    memory_dir = cfg.contextos_dir / "memory"
    embedder   = get_embedder()
    fragment   = write_fragment(
        memory_dir      = memory_dir,
        user_id         = request.user_id,
        content         = request.content,
        fragment_type   = request.type.value,
        importance      = request.importance,
        source_client   = request.source_client,
        project         = request.project,
        tags            = request.tags,
        supersedes_id   = request.supersedes_id,
    )
    return {"fragment_id": fragment["id"], "user_id": fragment["user_id"]}


@app.post("/memory/query")
def memory_query(
    request: QueryMemoryRequest,
    _token=Depends(require_scope(TokenScope.read)),
):
    """Query memory fragments for a user. Ranked by importance × decay × similarity."""
    from contextos.user_memory import query_fragments
    cfg      = get_config()
    embedder = get_embedder()
    results  = query_fragments(
        memory_dir       = cfg.contextos_dir / "memory",
        user_id          = request.user_id,
        query            = request.query,
        embedder         = embedder,
        project          = request.project,
        fragment_type    = request.type.value if request.type else None,
        limit            = request.limit,
        min_importance   = request.min_importance,
        include_superseded = request.include_superseded,
    )
    return {"fragments": results, "count": len(results)}


@app.get("/memory/stats")
def memory_stats(
    user_id: str = Query(...),
    _token=Depends(require_scope(TokenScope.read)),
):
    """Return memory statistics for a user."""
    from contextos.user_memory import get_stats
    cfg = get_config()
    return get_stats(cfg.contextos_dir / "memory", user_id)


@app.get("/memory/users")
def memory_users(_token=Depends(require_scope(TokenScope.admin))):
    """List all user_ids with stored memory. Admin scope."""
    from contextos.user_memory import list_users
    cfg = get_config()
    return {"users": list_users(cfg.contextos_dir / "memory")}


@app.delete("/admin/memory")
def memory_delete_user(
    user_id: str = Query(...),
    _token=Depends(require_scope(TokenScope.admin)),
):
    """GDPR bulk delete: remove all memory for a user. Admin scope."""
    from contextos.user_memory import delete_user_memory
    cfg = get_config()
    return delete_user_memory(cfg.contextos_dir / "memory", user_id)


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
    _token=Depends(require_scope(TokenScope.read)),
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
    """Start uvicorn server. ALWAYS binds to 127.0.0.1."""
    import uvicorn
    # Warm up embedding model in background — eliminates cold-start on first search
    try:
        emb = get_embedder()
        emb.warmup()
        logger.info("Embedding model warmup started in background")
    except Exception as exc:
        logger.debug("Warmup skipped: %s", exc)

    uvicorn.run(
        "contextos.api:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        reload=False,
    )
