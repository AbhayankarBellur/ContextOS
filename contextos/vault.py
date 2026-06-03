"""
ContextOS vault.py — Filesystem scanner and frontmatter parser.
Read-only: ContextOS never writes to vault documents.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import frontmatter

from contextos.schema import Document, DocumentStatus, DocumentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_of_path(path: Path, root: Path) -> str:
    """Generate a stable ID from the relative path."""
    rel = str(path.relative_to(root)).replace("\\", "/")
    return hashlib.sha256(rel.encode()).hexdigest()


def _sha256_of_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _extract_title(content: str, filepath: Path) -> str:
    """Extract first H1 heading or fall back to filename stem."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return filepath.stem.replace("-", " ").replace("_", " ").title()


def _parse_document_type(raw: Optional[str]) -> DocumentType:
    if raw is None:
        return DocumentType.note
    try:
        return DocumentType(raw.lower().strip())
    except ValueError:
        logger.warning("Unknown document type '%s', defaulting to 'note'", raw)
        return DocumentType.note


def _parse_document_status(raw: Optional[str]) -> DocumentStatus:
    if raw is None:
        return DocumentStatus.draft
    try:
        return DocumentStatus(raw.lower().strip())
    except ValueError:
        logger.warning("Unknown document status '%s', defaulting to 'draft'", raw)
        return DocumentStatus.draft


def _parse_date(raw) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def _parse_tags(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_document(filepath: Path, root: Path) -> Optional[Document]:
    """
    Parse a single Markdown file into a Document.
    Returns None if the file cannot be read.
    Logs warnings for missing/invalid frontmatter fields.
    """
    try:
        raw_content = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Cannot read '%s': %s", filepath, exc)
        return None

    try:
        post = frontmatter.loads(raw_content)
    except Exception as exc:
        logger.warning("Frontmatter parse failed for '%s': %s — treating as plain markdown", filepath, exc)
        post = frontmatter.Post(raw_content, **{})

    meta = post.metadata
    content = post.content

    # Validate required fields
    project = meta.get("project")
    if not project:
        logger.warning("Missing 'project' in frontmatter of '%s' — using directory name", filepath)
        project = filepath.parent.parent.name or "unknown"

    doc_type = _parse_document_type(meta.get("type"))
    status = _parse_document_status(meta.get("status"))
    doc_id = _sha256_of_path(filepath, root)

    return Document(
        id=doc_id,
        project=str(project),
        type=doc_type,
        domain=meta.get("domain"),
        status=status,
        owner=meta.get("owner"),
        updated_at=_parse_date(meta.get("updated_at")),
        tags=_parse_tags(meta.get("tags")),
        title=_extract_title(content, filepath),
        filepath=filepath,
        content=raw_content,  # full raw markdown including frontmatter
    )


def scan_vault(vault_path: Path) -> list[Document]:
    """
    Walk a vault directory, parse all .md files, return Document list.
    Skips files in hidden directories and .contextos/.
    """
    vault_path = vault_path.resolve()
    if not vault_path.exists():
        logger.error("Vault path does not exist: %s", vault_path)
        return []

    documents: list[Document] = []
    skipped = 0

    for md_file in vault_path.rglob("*.md"):
        # Skip hidden dirs and .contextos internals
        parts = md_file.parts
        if any(p.startswith(".") for p in parts):
            continue

        doc = parse_document(md_file, vault_path)
        if doc:
            documents.append(doc)
        else:
            skipped += 1

    logger.info("Scanned %d documents from '%s' (%d skipped)", len(documents), vault_path, skipped)
    return documents


def write_registry(documents: list[Document], metadata_dir: Path) -> Path:
    """Serialize document registry to metadata/registry.json."""
    metadata_dir.mkdir(parents=True, exist_ok=True)
    registry_path = metadata_dir / "registry.json"

    records = []
    for doc in documents:
        records.append({
            "id": doc.id,
            "project": doc.project,
            "type": doc.type.value,
            "domain": doc.domain,
            "status": doc.status.value,
            "owner": doc.owner,
            "updated_at": str(doc.updated_at) if doc.updated_at else None,
            "tags": doc.tags,
            "title": doc.title,
            "filepath": str(doc.filepath),
            "content_hash": _sha256_of_content(doc.content),
        })

    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info("Registry written to %s (%d documents)", registry_path, len(records))
    return registry_path


def load_registry(metadata_dir: Path) -> list[dict]:
    """Load registry from metadata/registry.json."""
    registry_path = metadata_dir / "registry.json"
    if not registry_path.exists():
        return []
    with open(registry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_content_hash(filepath: Path) -> Optional[str]:
    """Return SHA-256 of a file's content for change detection."""
    try:
        content = filepath.read_text(encoding="utf-8")
        return _sha256_of_content(content)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Incremental index hash store
# ---------------------------------------------------------------------------

def load_hash_store(metadata_dir: Path) -> dict[str, str]:
    """Load the persisted {doc_id: content_hash} map."""
    hash_file = metadata_dir / "hashes.json"
    if not hash_file.exists():
        return {}
    try:
        with open(hash_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_hash_store(metadata_dir: Path, hashes: dict[str, str]) -> None:
    """Persist the {doc_id: content_hash} map."""
    metadata_dir.mkdir(parents=True, exist_ok=True)
    hash_file = metadata_dir / "hashes.json"
    with open(hash_file, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2)


def compute_changed_documents(
    documents: list,
    metadata_dir: Path,
) -> tuple[list, list, list]:
    """
    Compare current document content hashes against stored hashes.

    Returns:
        (new_docs, changed_docs, unchanged_docs)
        new_docs      — never seen before
        changed_docs  — content hash differs from stored
        unchanged_docs — hash matches; skip re-embedding
    """
    stored = load_hash_store(metadata_dir)
    new_docs, changed_docs, unchanged_docs = [], [], []

    for doc in documents:
        current_hash = _sha256_of_content(doc.content)
        if doc.id not in stored:
            new_docs.append(doc)
        elif stored[doc.id] != current_hash:
            changed_docs.append(doc)
        else:
            unchanged_docs.append(doc)

    return new_docs, changed_docs, unchanged_docs


def update_hash_store(metadata_dir: Path, documents: list) -> None:
    """Update stored hashes for a list of documents."""
    stored = load_hash_store(metadata_dir)
    for doc in documents:
        stored[doc.id] = _sha256_of_content(doc.content)
    save_hash_store(metadata_dir, stored)
