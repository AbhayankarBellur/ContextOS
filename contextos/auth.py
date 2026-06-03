"""
ContextOS auth.py — Token generation, SHA-256 hashing, validation, scopes.
Raw token values are printed once at creation and NEVER stored in plaintext.
Only SHA-256 hash is persisted in .contextos/tokens/<id>.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from contextos.schema import Token, TokenScope

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "ctx_"
RATE_LIMIT_WINDOW = 60   # seconds
DEFAULT_RATE_LIMIT = 1000  # requests per window


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash of the raw token value."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _token_file(tokens_dir: Path, token_id: str) -> Path:
    return tokens_dir / f"{token_id}.json"


def generate_token(
    name: str,
    tokens_dir: Path,
    scope: TokenScope = TokenScope.write,
    expires_days: Optional[int] = None,
) -> tuple[str, Token]:
    """
    Generate a new API token.
    Returns (raw_token, Token).
    raw_token is returned ONCE — never stored in plaintext.
    Only SHA-256 hash is persisted.
    """
    tokens_dir.mkdir(parents=True, exist_ok=True)

    raw_token = TOKEN_PREFIX + secrets.token_hex(16)
    token_id  = TOKEN_PREFIX + secrets.token_hex(8)

    expires_at = None
    if expires_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    token = Token(
        id=token_id,
        name=name,
        hash=_hash_token(raw_token),
        created_at=datetime.now(timezone.utc),
        last_used=None,
        revoked=False,
        scope=scope,
        expires_at=expires_at,
        request_count=0,
    )

    token_data = token.model_dump()
    token_data["created_at"]  = token.created_at.isoformat()
    token_data["last_used"]   = None
    token_data["expires_at"]  = expires_at.isoformat() if expires_at else None
    token_data["scope"]       = scope.value

    with open(_token_file(tokens_dir, token_id), "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    logger.info("Token created: %s (%s) scope=%s", token_id, name, scope.value)
    return raw_token, token


def validate_token(raw_token: str, tokens_dir: Path) -> Optional[Token]:
    """
    Validate a raw Bearer token.
    Returns Token if valid, not revoked, and not expired.
    Updates last_used and request_count on success.
    """
    if not raw_token.startswith(TOKEN_PREFIX):
        return None

    token_hash = _hash_token(raw_token)

    if not tokens_dir.exists():
        return None

    for token_file in tokens_dir.glob("*.json"):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("hash") != token_hash:
                continue

            if data.get("revoked", False):
                logger.warning("Attempt to use revoked token: %s", data.get("id"))
                return None

            # Check expiry
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) > expires_at:
                    logger.warning("Expired token used: %s", data.get("id"))
                    return None

            # Update last_used and request_count
            data["last_used"]     = datetime.now(timezone.utc).isoformat()
            data["request_count"] = data.get("request_count", 0) + 1
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return _dict_to_token(data)

        except Exception as exc:
            logger.error("Error reading token file %s: %s", token_file, exc)
            continue

    return None


def check_rate_limit(
    token: Token,
    tokens_dir: Path,
    limit: int = DEFAULT_RATE_LIMIT,
) -> bool:
    """
    Check if this token has exceeded its rate limit.
    Sliding window: resets after RATE_LIMIT_WINDOW seconds.
    Returns True if within limit, False if exceeded.
    """
    token_file = _token_file(tokens_dir, token.id)
    if not token_file.exists():
        return True

    try:
        with open(token_file) as f:
            data = json.load(f)

        now = time.time()
        window_start = data.get("rate_window_start", now)
        window_count = data.get("rate_window_count", 0)

        # Reset window if expired
        if now - window_start > RATE_LIMIT_WINDOW:
            window_start = now
            window_count = 0

        window_count += 1
        within_limit = window_count <= limit

        data["rate_window_start"] = window_start
        data["rate_window_count"] = window_count
        with open(token_file, "w") as f:
            json.dump(data, f, indent=2)

        return within_limit
    except Exception:
        return True  # fail open — don't block on rate limit errors


def check_scope(token: Token, required: TokenScope) -> bool:
    """Return True if token has sufficient scope for the required level."""
    return token.has_scope(required)


def revoke_token(token_id: str, tokens_dir: Path) -> bool:
    """
    Immediately revoke a token by ID.
    Returns True if found and revoked, False if not found.
    """
    token_file = _token_file(tokens_dir, token_id)
    if not token_file.exists():
        return False

    try:
        with open(token_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["revoked"] = True
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Token revoked: %s", token_id)
        return True
    except Exception as exc:
        logger.error("Failed to revoke token %s: %s", token_id, exc)
        return False


def list_tokens(tokens_dir: Path) -> list[Token]:
    """
    List all tokens. NEVER returns raw token values.
    Returns sorted by created_at descending.
    """
    if not tokens_dir.exists():
        return []

    tokens = []
    for token_file in tokens_dir.glob("*.json"):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tokens.append(_dict_to_token(data))
        except Exception as exc:
            logger.error("Failed to read token file %s: %s", token_file, exc)

    tokens.sort(key=lambda t: t.created_at, reverse=True)
    return tokens


def _dict_to_token(data: dict) -> Token:
    """Convert a stored token dict to a Token object."""
    created_at = data.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)

    last_used = data.get("last_used")
    if isinstance(last_used, str):
        last_used = datetime.fromisoformat(last_used)

    expires_at = data.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)

    scope_str = data.get("scope")
    scope = TokenScope(scope_str) if scope_str else TokenScope.write

    return Token(
        id=data["id"],
        name=data["name"],
        hash=data["hash"],
        created_at=created_at,
        last_used=last_used,
        revoked=data.get("revoked", False),
        scope=scope,
        expires_at=expires_at,
        request_count=data.get("request_count", 0),
    )
