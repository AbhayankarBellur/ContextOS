"""
ContextOS mcp_server.py — MCP (Model Context Protocol) server.
Exposes ContextOS as native tools for Claude Code, Cursor, Continue.dev, and
any other MCP-compatible AI coding agent.

Tools exposed:
  search_knowledge   — semantic search across vault docs
  get_context        — assembled context block for a task
  grep_codebase      — fast regex/literal search across source files
  read_file          — read a file with optional line range
  get_graph          — knowledge graph summary
  get_status         — index health check

Usage:
  context mcp                    # stdio transport (for most agents)
  context mcp --port 8766        # SSE transport (for browser-based agents)
"""
from __future__ import annotations

import json
import logging
import re as re_mod
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool handler implementations — pure functions, no FastAPI dependency
# ---------------------------------------------------------------------------

def _get_cfg():
    from contextos.config import load_config
    return load_config()


def tool_search_knowledge(
    query: str,
    project: Optional[str] = None,
    doc_type: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """Semantic search across indexed vault documents."""
    cfg = _get_cfg()
    from contextos.embedder import Embedder
    from contextos.store import VectorStore

    embedder = Embedder(cfg.embeddings_dir)
    store = VectorStore(cfg.lancedb_dir)
    qv = embedder.embed_query(query)
    results = store.search(
        query_vector=qv,
        project=project,
        type_filter=doc_type,
        domain_filter=domain,
        limit=max(1, min(20, limit)),
    )

    formatted = []
    for r in results:
        score = max(0.0, 1.0 - float(r.get("_distance", 1.0)))
        formatted.append({
            "title":    r.get("title", ""),
            "type":     r.get("type", ""),
            "domain":   r.get("domain", "") or None,
            "score":    round(score, 4),
            "section":  r.get("heading", ""),
            "content":  r.get("content", "")[:800],
            "filepath": r.get("filepath", ""),
        })

    return {
        "query":   query,
        "results": formatted,
        "count":   len(formatted),
    }


def tool_get_context(
    query: str,
    project: Optional[str] = None,
    max_tokens: int = 4000,
) -> dict:
    """Assemble a ready-to-use context block for an agent task."""
    cfg = _get_cfg()
    from contextos.embedder import Embedder
    from contextos.store import VectorStore
    from contextos.graph import GraphBuilder
    from contextos.retrieval import assemble_context

    embedder = Embedder(cfg.embeddings_dir)
    store    = VectorStore(cfg.lancedb_dir)
    gb       = GraphBuilder()
    gb.load(cfg.graph_dir)

    result = assemble_context(
        query=query,
        embedder=embedder,
        store=store,
        graph_builder=gb,
        project=project,
        max_tokens=max_tokens,
    )

    return {
        "context":        result.context,
        "token_estimate": result.token_estimate,
        "sources":        result.sources,
        "source_count":   len(result.sources),
    }


def tool_grep_codebase(
    pattern: str,
    search_path: str = ".",
    file_type: Optional[str] = None,
    literal: bool = False,
    max_results: int = 50,
) -> dict:
    """Fast regex/literal search across codebase files."""
    import time
    t0 = time.time()
    sp = Path(search_path).resolve()
    if not sp.exists():
        return {"error": f"Path not found: {sp}", "matches": [], "total": 0}

    matches = []
    rg_ok = False
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        rg_ok = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if rg_ok:
        cmd = ["rg", "--json", "--context=2", f"--max-count={max_results}"]
        if literal: cmd.append("--fixed-strings")
        if file_type: cmd += [f"--type={file_type}"]
        cmd += [pattern, str(sp)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            for line in r.stdout.splitlines():
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "match":
                        m = obj["data"]
                        matches.append({
                            "file":    m["path"]["text"],
                            "line":    m["line_number"],
                            "content": m["lines"]["text"].rstrip(),
                        })
                except Exception:
                    pass
        except Exception:
            rg_ok = False

    if not rg_ok:
        flags = 0 if literal else re_mod.IGNORECASE
        ext = f".{file_type}" if file_type else None
        for f in sp.rglob("*"):
            if ext and f.suffix != ext: continue
            if any(p.startswith(".") for p in f.parts): continue
            if not f.is_file(): continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                for i, line in enumerate(lines):
                    if (pattern in line) if literal else bool(re_mod.search(pattern, line, flags)):
                        matches.append({"file": str(f), "line": i + 1, "content": line.rstrip()})
                        if len(matches) >= max_results: break
            except Exception:
                pass
            if len(matches) >= max_results: break

    return {
        "pattern":    pattern,
        "matches":    matches[:max_results],
        "total":      len(matches),
        "latency_ms": int((time.time() - t0) * 1000),
        "engine":     "ripgrep" if rg_ok else "python",
    }


def tool_read_file(
    filepath: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> dict:
    """Read a file with optional line range. Returns content + metadata."""
    import hashlib
    fp = Path(filepath).resolve()
    if not fp.exists():
        return {"error": f"File not found: {fp}"}

    try:
        content = fp.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"error": str(e)}

    all_lines = content.splitlines()
    total = len(all_lines)
    s = (start_line - 1) if start_line else 0
    e = end_line if end_line else total
    sliced = "\n".join(all_lines[s:e])

    ext = fp.suffix.lstrip(".")
    lang_map = {"py": "python", "ts": "typescript", "js": "javascript",
                "md": "markdown", "rs": "rust", "go": "go", "java": "java"}
    return {
        "filepath":      str(fp),
        "content":       sliced,
        "total_lines":   total,
        "lines_shown":   f"{s+1}–{min(e, total)}",
        "language":      lang_map.get(ext, ext or "unknown"),
        "size_bytes":    fp.stat().st_size,
        "content_hash":  hashlib.sha256(content.encode()).hexdigest()[:16],
    }


def tool_get_graph() -> dict:
    """Return knowledge graph summary and top nodes."""
    cfg = _get_cfg()
    from contextos.graph import GraphBuilder
    gb = GraphBuilder()
    gb.load(cfg.graph_dir)
    summary = gb.get_summary()

    graph_path = cfg.graph_dir / "graph.json"
    nodes = []
    if graph_path.exists():
        data = json.loads(graph_path.read_text())
        nodes = [
            {"id": n["id"], "title": n.get("title", ""), "type": n.get("type", ""),
             "domain": n.get("domain", "")}
            for n in data.get("nodes", [])[:20]
        ]

    return {
        "nodes":        summary.get("nodes", 0),
        "edges":        summary.get("edges", 0),
        "types":        summary.get("types", {}),
        "relations":    summary.get("relations", {}),
        "sample_nodes": nodes,
    }


def tool_get_status() -> dict:
    """Return index health — document count, last indexed, model."""
    cfg = _get_cfg()
    meta_file = cfg.metadata_dir / "index_meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    return {
        "status":           "ok",
        "document_count":   meta.get("document_count", 0),
        "chunk_count":      meta.get("chunk_count", 0),
        "last_indexed":     meta.get("last_indexed", "never"),
        "embedding_model":  meta.get("embedding_model", "BAAI/bge-small-en-v1.5"),
        "version":          "1.1.0-rc1",
        "vault_paths":      [str(p) for p in cfg.vault_paths],
    }


# ---------------------------------------------------------------------------
# MCP Server — stdio transport
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "search_knowledge",
        "description": (
            "Semantic search across the ContextOS knowledge vault. "
            "Use this to find architecture docs, ADRs, domain models, workflows, "
            "and sprint context relevant to your current task. "
            "Always call this before starting a coding task."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string", "description": "Natural language search query"},
                "project": {"type": "string", "description": "Filter by project name (optional)"},
                "doc_type":{"type": "string", "description": "Filter by type: architecture|adr|domain|workflow|product|context|note"},
                "domain":  {"type": "string", "description": "Filter by domain (optional)"},
                "limit":   {"type": "integer", "description": "Number of results (1-20)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_context",
        "description": (
            "Assemble a complete, prioritised context block for an agent task. "
            "Returns a Markdown string with architecture decisions, domain models, "
            "and current sprint context — packed within a token budget. "
            "Use this as your pre-task context injection."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string", "description": "Task description to fetch context for"},
                "project":    {"type": "string", "description": "Project name (optional)"},
                "max_tokens": {"type": "integer", "description": "Token budget (default: 4000)", "default": 4000},
            },
            "required": ["query"],
        },
    },
    {
        "name": "grep_codebase",
        "description": (
            "Fast regex or literal search across source files. "
            "Use to find function definitions, class usages, import patterns, "
            "or any text pattern across the codebase. "
            "Much faster than reading files one by one."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern":     {"type": "string", "description": "Regex or literal pattern to search for"},
                "search_path": {"type": "string", "description": "Directory to search (default: .)", "default": "."},
                "file_type":   {"type": "string", "description": "File extension filter e.g. py, ts, js"},
                "literal":     {"type": "boolean", "description": "Treat pattern as literal string", "default": False},
                "max_results": {"type": "integer", "description": "Max matches to return", "default": 50},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a source file with optional line range. "
            "Use when you need to inspect specific sections of a file. "
            "Prefer grep_codebase for finding patterns, use read_file for reading known sections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath":   {"type": "string", "description": "Absolute or relative file path"},
                "start_line": {"type": "integer", "description": "First line to return (1-indexed)"},
                "end_line":   {"type": "integer", "description": "Last line to return (inclusive)"},
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "get_graph",
        "description": (
            "Return the knowledge graph summary: node types, edge relationships, "
            "and a sample of nodes. Use to understand how project concepts relate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_status",
        "description": (
            "Check ContextOS index health: document count, last indexed time, "
            "embedding model, and registered vault paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

TOOL_HANDLERS = {
    "search_knowledge": lambda args: tool_search_knowledge(**args),
    "get_context":      lambda args: tool_get_context(**args),
    "grep_codebase":    lambda args: tool_grep_codebase(**args),
    "read_file":        lambda args: tool_read_file(**args),
    "get_graph":        lambda _:    tool_get_graph(),
    "get_status":       lambda _:    tool_get_status(),
}

# Minimum token scope required per tool
TOOL_SCOPES = {
    "search_knowledge": "read",
    "get_context":      "read",
    "grep_codebase":    "read",
    "read_file":        "read",
    "get_graph":        "read",
    "get_status":       "read",
}


def _validate_mcp_token(raw_token: Optional[str]) -> Optional[object]:
    """Validate token from env var for MCP calls. Returns Token or None."""
    if not raw_token:
        return None
    try:
        from contextos.auth import validate_token
        from contextos.config import load_config
        cfg = load_config()
        return validate_token(raw_token, cfg.tokens_dir)
    except Exception:
        return None


def run_mcp_server():
    """
    Start the MCP server using stdio transport.
    Compatible with Claude Code, Cursor, Continue.dev, and any MCP client.
    """
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
        import asyncio
    except ImportError:
        print("ERROR: mcp package not installed. Run: pip install mcp")
        raise SystemExit(1)

    server = Server("contextos")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        # Token scope enforcement
        raw_token = os.environ.get("CONTEXTOS_TOKEN", "")
        token = _validate_mcp_token(raw_token)
        required_scope = TOOL_SCOPES.get(name, "read")

        if token is None:
            return [types.TextContent(type="text", text=json.dumps({
                "error": "unauthorized",
                "message": "CONTEXTOS_TOKEN env var missing or invalid. "
                           "Run: context token create agent --scope read"
            }))]

        if token.is_expired():
            return [types.TextContent(type="text", text=json.dumps({
                "error": "token_expired",
                "message": f"Token {token.id} has expired. Create a new one."
            }))]

        from contextos.schema import TokenScope
        if not token.has_scope(TokenScope(required_scope)):
            return [types.TextContent(type="text", text=json.dumps({
                "error": "insufficient_scope",
                "message": f"Tool '{name}' requires scope '{required_scope}', "
                           f"token has '{token.scope.value if token.scope else 'none'}'"
            }))]

        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = handler(arguments)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return [types.TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    async def _main():
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(_main())
