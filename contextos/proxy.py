"""
ContextOS proxy.py — Context proxy mode.

Sits between IDE/agent and cloud LLM. Automatically:
  1. Classifies conversation turns: HOT/WARM/COLD/DEAD
  2. Compresses COLD turns with extractive summarisation (sumy/TF-IDF)
  3. Drops DEAD turns (duplicates, empty, noise)
  4. Injects ContextOS vault context before the request

Zero change to IDE config after adding the proxy URL.
IDE sends to http://127.0.0.1:9137/v1  (proxy)
Proxy cleans context, injects vault context, forwards to real LLM API.

Start: context proxy start --target https://api.openai.com --project my-project
"""
from __future__ import annotations

import json
import logging
import time
import hashlib
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

logger = logging.getLogger(__name__)

PROXY_PORT_DEFAULT = 9137


class TurnHeat(str, Enum):
    HOT  = "hot"    # last 5 turns — kept verbatim
    WARM = "warm"   # turns 6-15 — kept verbatim
    COLD = "cold"   # older — compressed with extractive summariser
    DEAD = "dead"   # duplicates, empty, system noise — dropped


def classify_turn(turn_index_from_end: int, content: str) -> TurnHeat:
    """
    Classify a conversation turn by its heat.
    turn_index_from_end: 0 = most recent, 1 = second most recent, etc.
    """
    if not content or not content.strip():
        return TurnHeat.DEAD
    if turn_index_from_end <= 4:
        return TurnHeat.HOT
    if turn_index_from_end <= 14:
        return TurnHeat.WARM
    return TurnHeat.COLD


def is_duplicate(content: str, seen_hashes: set) -> bool:
    h = hashlib.md5(content.strip().lower().encode()).hexdigest()
    if h in seen_hashes:
        return True
    seen_hashes.add(h)
    return False


def compress_turn(content: str, ratio: float = 0.4) -> str:
    """Extractive compression using sumy TF-IDF (already installed)."""
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lsa import LsaSummarizer
        from sumy.nlp.stemmers import Stemmer
        from sumy.utils import get_stop_words

        parser     = PlaintextParser.from_string(content, Tokenizer("english"))
        sentences  = list(parser.document.sentences)
        if len(sentences) <= 2:
            return content

        keep_n     = max(1, int(len(sentences) * ratio))
        stemmer    = Stemmer("english")
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words("english")
        result     = summarizer(parser.document, keep_n)
        return " ".join(str(s) for s in result) or content[:200]
    except Exception:
        # Hard fallback: first 40% of chars
        keep = max(100, int(len(content) * ratio))
        return content[:keep] + "…"


def process_messages(
    messages: list[dict],
    project: Optional[str],
    vault_query: Optional[str],
    embedder=None,
    store=None,
) -> tuple[list[dict], dict]:
    """
    Process a message list:
    1. Classify each turn by heat
    2. Drop DEAD turns
    3. Compress COLD turns
    4. Inject vault context as a system message

    Returns (processed_messages, stats)
    """
    if not messages:
        return messages, {}

    stats = {"total": len(messages), "hot": 0, "warm": 0, "cold": 0, "dead": 0,
             "tokens_original": 0, "tokens_after": 0}

    # Classify from most recent backward
    seen_hashes: set = set()
    classifications = []
    for i, msg in enumerate(reversed(messages)):
        content = msg.get("content", "") or ""
        stats["tokens_original"] += len(content) // 4

        if is_duplicate(content, seen_hashes):
            classifications.append((len(messages) - 1 - i, TurnHeat.DEAD))
        else:
            heat = classify_turn(i, content)
            classifications.append((len(messages) - 1 - i, heat))

    heat_map = {idx: heat for idx, heat in classifications}

    processed = []
    for i, msg in enumerate(messages):
        heat    = heat_map.get(i, TurnHeat.HOT)
        content = msg.get("content", "") or ""
        role    = msg.get("role", "user")

        stats[heat.value] += 1

        if heat == TurnHeat.DEAD:
            continue  # drop silently
        elif heat == TurnHeat.COLD and role not in ("system",):
            compressed = compress_turn(content)
            processed.append({**msg, "content": f"[summary] {compressed}"})
            stats["tokens_after"] += len(compressed) // 4
        else:
            processed.append(msg)
            stats["tokens_after"] += len(content) // 4

    # Inject vault context as system message
    if vault_query and embedder and store:
        try:
            qv  = embedder.embed_query(vault_query)
            results = store.hybrid_search(
                query_text=vault_query, query_vector=qv,
                project=project, limit=3, alpha=0.7
            )
            if results:
                ctx_parts = []
                for r in results:
                    ctx_parts.append(f"### {r.get('title','')}\n{r.get('content','')[:400]}")
                vault_context = "## Project Context (from ContextOS)\n\n" + "\n\n".join(ctx_parts)
                # Inject after first system message or at start
                inject_pos = 0
                for j, m in enumerate(processed):
                    if m.get("role") == "system":
                        inject_pos = j + 1
                        break
                processed.insert(inject_pos, {
                    "role": "system",
                    "content": vault_context,
                })
                stats["vault_injected"] = True
                stats["vault_chunks"]   = len(results)
        except Exception as exc:
            logger.debug("Vault injection failed: %s", exc)

    stats["tokens_saved"]   = max(0, stats["tokens_original"] - stats["tokens_after"])
    stats["compression_pct"]= round(
        stats["tokens_saved"] / max(1, stats["tokens_original"]) * 100, 1
    )
    return processed, stats


# ---------------------------------------------------------------------------
# Proxy FastAPI app
# ---------------------------------------------------------------------------

proxy_app = FastAPI(title="ContextOS Proxy", version="1.5.0")

# Global state (set when proxy starts)
_proxy_target: str = "https://api.openai.com"
_proxy_project: Optional[str] = None
_proxy_embedder = None
_proxy_store    = None
_proxy_stats    = {"requests": 0, "tokens_saved_total": 0, "sessions": []}


@proxy_app.get("/health")
def proxy_health():
    return {
        "status":       "ok",
        "proxy_target": _proxy_target,
        "project":      _proxy_project,
        "stats":        _proxy_stats,
    }


@proxy_app.get("/proxy/stats")
def proxy_stats_endpoint():
    """Return proxy session statistics."""
    return _proxy_stats


@proxy_app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","OPTIONS","HEAD"])
async def proxy_forward(path: str, request: Request):
    """
    Intercept all requests. For chat completion endpoints,
    process the messages. Forward everything else unchanged.
    """
    try:
        import httpx
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="httpx not installed. Run: pip install contextos-vault[proxy]"
        )

    body_bytes = await request.body()
    is_chat    = "chat/completions" in path

    processed_body = body_bytes
    session_stats  = {}

    if is_chat and body_bytes:
        try:
            data     = json.loads(body_bytes)
            messages = data.get("messages", [])
            if messages:
                # Use last user message as vault query
                last_user = next(
                    (m.get("content","") for m in reversed(messages)
                     if m.get("role") == "user"), ""
                )
                processed_msgs, session_stats = process_messages(
                    messages    = messages,
                    project     = _proxy_project,
                    vault_query = last_user[:200] if last_user else None,
                    embedder    = _proxy_embedder,
                    store       = _proxy_store,
                )
                data["messages"] = processed_msgs
                processed_body   = json.dumps(data).encode()

                # Accumulate stats
                _proxy_stats["requests"] += 1
                _proxy_stats["tokens_saved_total"] += session_stats.get("tokens_saved", 0)
                _proxy_stats["sessions"].append({
                    "ts":          time.strftime("%H:%M:%S"),
                    "saved":       session_stats.get("tokens_saved", 0),
                    "compression": session_stats.get("compression_pct", 0),
                    "heat":        {k: session_stats.get(k,0)
                                    for k in ("hot","warm","cold","dead")},
                })
                if len(_proxy_stats["sessions"]) > 100:
                    _proxy_stats["sessions"] = _proxy_stats["sessions"][-100:]

        except Exception as exc:
            logger.debug("Proxy message processing failed: %s", exc)
            processed_body = body_bytes

    # Forward to target
    target_url = f"{_proxy_target.rstrip('/')}/{path}"
    headers    = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.request(
                method  = request.method,
                url     = target_url,
                headers = headers,
                content = processed_body,
                params  = dict(request.query_params),
            )
            response_headers = dict(resp.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("transfer-encoding", None)
            if session_stats:
                response_headers["X-ContextOS-Tokens-Saved"] = str(
                    session_stats.get("tokens_saved", 0)
                )
            return JSONResponse(
                content=resp.json() if resp.headers.get("content-type","").startswith("application/json") else {},
                status_code=resp.status_code,
                headers=response_headers,
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Proxy forward failed: {exc}")


def run_proxy(
    port: int = PROXY_PORT_DEFAULT,
    target: str = "https://api.openai.com",
    project: Optional[str] = None,
    vault_root: Optional[Path] = None,
):
    """Start the ContextOS proxy server."""
    global _proxy_target, _proxy_project, _proxy_embedder, _proxy_store

    _proxy_target  = target
    _proxy_project = project

    # Load vault components if available
    if vault_root and (vault_root / ".contextos").exists():
        try:
            from contextos.config import load_config
            from contextos.embedder import Embedder
            from contextos.store import VectorStore
            cfg              = load_config(vault_root)
            _proxy_embedder  = Embedder(cfg.embeddings_dir)
            _proxy_store     = VectorStore(cfg.lancedb_dir)
            logger.info("Proxy: vault loaded from %s", vault_root)
        except Exception as exc:
            logger.warning("Proxy: vault load failed (%s) — context injection disabled", exc)

    logger.info("Proxy starting on 127.0.0.1:%d → %s", port, target)
    uvicorn.run(proxy_app, host="127.0.0.1", port=port, log_level="warning")
