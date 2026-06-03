"""
ContextOS auth.py — Token generation, SHA-256 hashing, and validation.
Raw token values are printed once at creation and NEVER stored in plaintext.
Only SHA-256 hash is persisted in .contextos/tokens/<id>.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from contextos.schema import Token

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "ctx_"


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash of the raw token value."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _token_file(tokens_dir: Path, token_id: str) -> Path:
    return tokens_dir / f"{token_id}.json"


def generate_token(name: str, tokens_dir: Path) -> tuple[str, Token]:
    """
    Generate a new API token.
    Returns (raw_token, Token).
    raw_token is returned ONCE — never stored in plaintext.
    Only SHA-256 hash is persisted.
    """
    tokens_dir.mkdir(parents=True, exist_ok=True)

    # Generate: ctx_ + 32 random hex chars
    raw_token = TOKEN_PREFIX + secrets.token_hex(16)
    token_id = TOKEN_PREFIX + secrets.token_hex(8)

    token = Token(
        id=token_id,
        name=name,
        hash=_hash_token(raw_token),
        created_at=datetime.now(timezone.utc),
        last_used=None,
        revoked=False,
    )

    # Write to .contextos/tokens/<id>.json — hash only, no raw value
    token_data = token.model_dump()
    token_data["created_at"] = token.created_at.isoformat()
    token_data["last_used"] = None

    with open(_token_file(tokens_dir, token_id), "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    logger.info("Token created: %s (%s)", token_id, name)
    return raw_token, token


def validate_token(raw_token: str, tokens_dir: Path) -> Optional[Token]:
    """
    Validate a raw Bearer token.
    Returns Token if valid and not revoked, None otherwise.
    Updates last_used on successful validation.
    """
    if not raw_token.startswith(TOKEN_PREFIX):
        return None

    token_hash = _hash_token(raw_token)

    # Scan all token files for matching hash
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

            # Valid token — update last_used
            data["last_used"] = datetime.now(timezone.utc).isoformat()
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return _dict_to_token(data)

        except Exception as exc:
            logger.error("Error reading token file %s: %s", token_file, exc)
            continue

    return None


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

    return Token(
        id=data["id"],
        name=data["name"],
        hash=data["hash"],
        created_at=created_at,
        last_used=last_used,
        revoked=data.get("revoked", False),
    )
