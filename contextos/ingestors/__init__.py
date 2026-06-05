"""
ContextOS ingestors — document format extraction pipeline.

Each ingestor converts a binary/rich document format to plain Markdown
with YAML frontmatter, ready for the vault chunker and embedder.

Supported formats:
  .pdf   — pymupdf (fitz)  — text extraction per page
  .docx  — python-docx     — paragraph/heading/table → Markdown
  .pptx  — python-pptx     — slides → sectioned Markdown

Registry maps file extension → extractor function.
vault.py uses this registry when scanning non-Markdown files.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# Extension → (extract_function, requires_package)
_REGISTRY: dict[str, tuple[Callable, str]] = {}


def register(extension: str, package: str):
    """Decorator to register an ingestor for a file extension."""
    def decorator(fn: Callable):
        _REGISTRY[extension.lower()] = (fn, package)
        return fn
    return decorator


def can_ingest(path: Path) -> bool:
    return path.suffix.lower() in _REGISTRY


def ingest(path: Path) -> Optional[str]:
    """
    Extract text from a document file.
    Returns Markdown string with YAML frontmatter, or None on failure.
    """
    ext = path.suffix.lower()
    if ext not in _REGISTRY:
        return None
    fn, pkg = _REGISTRY[ext]
    try:
        return fn(path)
    except ImportError:
        logger.warning("Ingestor for %s requires '%s' — pip install %s", ext, pkg, pkg)
        return None
    except Exception as exc:
        logger.error("Ingestor failed for %s: %s", path, exc)
        return None


def supported_extensions() -> list[str]:
    return list(_REGISTRY.keys())


# Register built-in ingestors on import
from contextos.ingestors import pdf, docx, pptx   # noqa: E402, F401
