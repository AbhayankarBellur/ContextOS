"""
ContextOS connectors/base.py — Abstract base class for all connectors.

All connectors inherit BaseConnector and implement fetch().
fetch() returns a list of ConnectorResult, each of which is one Markdown
document to write to the vault output directory.
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ConnectorResult:
    """One document produced by a connector pull."""
    filename:    str          # e.g. "ISSUE-42.md"
    content:     str          # full Markdown with YAML frontmatter
    source_url:  str = ""     # original URL for attribution
    title:       str = ""
    doc_type:    str = "note" # DocumentType value
    domain:      str = ""

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


class BaseConnector(ABC):
    """
    Abstract connector. Subclasses implement fetch().
    """

    name: str = "base"
    description: str = ""

    def __init__(self, project: str, config: Optional[dict] = None):
        self.project = project
        self.config  = config or {}

    @abstractmethod
    def fetch(self) -> list[ConnectorResult]:
        """Pull data from the source. Returns list of ConnectorResult."""
        ...

    def write(
        self,
        results: list[ConnectorResult],
        output_dir: Path,
        force: bool = False,
    ) -> tuple[int, int, int]:
        """
        Write ConnectorResult list to output_dir.
        Skips files whose content hash hasn't changed (idempotent).

        Returns (written, skipped, total).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        written = skipped = 0

        for result in results:
            out_file = output_dir / result.filename

            # Idempotent: skip unchanged
            if not force and out_file.exists():
                existing_hash = hashlib.sha256(out_file.read_bytes()).hexdigest()
                if existing_hash == result.content_hash:
                    skipped += 1
                    continue

            out_file.write_text(result.content, encoding="utf-8")
            written += 1
            logger.debug("Wrote: %s", out_file)

        logger.info(
            "[%s] Written: %d  Skipped: %d  Total: %d",
            self.name, written, skipped, len(results)
        )
        return written, skipped, len(results)

    def pull(
        self,
        output_dir: Path,
        force: bool = False,
    ) -> dict:
        """
        Convenience method: fetch() + write().
        Returns summary dict.
        """
        results = self.fetch()
        written, skipped, total = self.write(results, output_dir, force=force)
        return {
            "connector": self.name,
            "project":   self.project,
            "total":     total,
            "written":   written,
            "skipped":   skipped,
            "output_dir": str(output_dir),
        }

    @staticmethod
    def _frontmatter(fields: dict) -> str:
        """Render a YAML frontmatter block."""
        lines = ["---"]
        for k, v in fields.items():
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            elif v is not None and v != "":
                lines.append(f"{k}: {v}")
        lines.append("---")
        return "\n".join(lines)
