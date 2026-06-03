"""
ContextOS connectors/json_source.py — Local JSON/YAML data connector.

Converts structured JSON or YAML files (configs, data exports, schemas)
into readable Markdown vault documents. Useful for:
  - Package.json / pyproject.toml dependency docs
  - Database schema exports
  - Config file documentation
  - Any structured local data

Usage:
  context pull json --source ./package.json
  context pull json --source ./db-schema.yaml --type domain
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from contextos.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

# Max keys to document before truncating
MAX_KEYS = 50
MAX_DEPTH = 3


class JSONConnector(BaseConnector):
    """Convert local JSON/YAML files into structured Markdown vault docs."""

    name        = "json"
    description = "Convert local JSON/YAML files into indexed vault documents"

    def __init__(self, project: str, config: Optional[dict] = None):
        super().__init__(project, config)
        self.source   = self.config.get("source", "")
        self.doc_type = self.config.get("type", "note")
        self.domain   = self.config.get("domain", "")

    def fetch(self) -> list[ConnectorResult]:
        if not self.source:
            raise ValueError("json connector requires 'source' config")

        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")

        results = []
        # Support glob patterns
        if "*" in str(path):
            for match in Path(".").glob(str(path)):
                r = self._process_file(match)
                if r:
                    results.append(r)
        else:
            r = self._process_file(path)
            if r:
                results.append(r)

        return results

    def _process_file(self, path: Path) -> Optional[ConnectorResult]:
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() in (".yaml", ".yml"):
                import yaml
                data = yaml.safe_load(text)
            elif path.suffix.lower() == ".toml":
                try:
                    import tomllib
                except ImportError:
                    try:
                        import tomli as tomllib  # type: ignore
                    except ImportError:
                        import tomllib  # Python 3.11+ stdlib
                data = tomllib.loads(text)
            else:
                data = json.loads(text)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", path, exc)
            return None

        # Special handling for known formats
        if path.name == "package.json":
            return self._npm_package(path, data)
        if path.name in ("pyproject.toml", "pyproject.json"):
            return self._pyproject(path, data)

        # Generic JSON/YAML doc
        return self._generic_doc(path, data)

    def _npm_package(self, path: Path, data: dict) -> ConnectorResult:
        name    = data.get("name","")
        version = data.get("version","")
        desc    = data.get("description","")
        deps    = data.get("dependencies", {})
        dev_deps= data.get("devDependencies", {})
        scripts = data.get("scripts", {})

        fm = self._frontmatter({
            "project":    self.project,
            "type":       "architecture",
            "domain":     "dependencies",
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["npm", "dependencies", "package"],
        })

        content  = f"{fm}\n\n# {name} v{version}\n\n"
        if desc: content += f"{desc}\n\n"
        if scripts:
            content += "## Scripts\n\n"
            for s, cmd in list(scripts.items())[:20]:
                content += f"- `{s}`: `{cmd}`\n"
            content += "\n"
        if deps:
            content += f"## Dependencies ({len(deps)})\n\n"
            for pkg, ver in list(deps.items())[:30]:
                content += f"- `{pkg}`: {ver}\n"
            content += "\n"
        if dev_deps:
            content += f"## Dev Dependencies ({len(dev_deps)})\n\n"
            for pkg, ver in list(dev_deps.items())[:20]:
                content += f"- `{pkg}`: {ver}\n"

        return ConnectorResult(
            filename = "npm-package.md",
            content  = content,
            title    = f"{name} package.json",
            doc_type = "architecture",
            domain   = "dependencies",
        )

    def _pyproject(self, path: Path, data: dict) -> ConnectorResult:
        proj    = data.get("project", data.get("tool", {}).get("poetry", {}))
        name    = proj.get("name","")
        version = proj.get("version","")
        desc    = proj.get("description","")
        deps    = proj.get("dependencies", [])

        fm = self._frontmatter({
            "project":    self.project,
            "type":       "architecture",
            "domain":     "dependencies",
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["python", "dependencies", "pyproject"],
        })

        content  = f"{fm}\n\n# {name} v{version}\n\n"
        if desc: content += f"{desc}\n\n"
        if deps:
            content += f"## Dependencies\n\n"
            dep_list = deps if isinstance(deps, list) else list(deps)
            for d in dep_list[:40]:
                content += f"- `{d}`\n"

        return ConnectorResult(
            filename = "pyproject-deps.md",
            content  = content,
            title    = f"{name} pyproject.toml",
            doc_type = "architecture",
            domain   = "dependencies",
        )

    def _generic_doc(self, path: Path, data) -> ConnectorResult:
        fm = self._frontmatter({
            "project":    self.project,
            "type":       self.doc_type,
            "domain":     self.domain or "",
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["data", path.suffix.lstrip(".")],
        })

        content = f"{fm}\n\n# {path.name}\n\n"
        content += f"**Source:** `{path}`  \n"
        content += f"**Format:** {path.suffix.upper().lstrip('.')}  \n\n"
        content += "## Contents\n\n"
        content += self._render_data(data, depth=0)

        return ConnectorResult(
            filename = f"data-{path.stem}.md",
            content  = content,
            title    = path.name,
            doc_type = self.doc_type,
            domain   = self.domain,
        )

    def _render_data(self, data, depth: int = 0) -> str:
        """Recursively render JSON/dict to Markdown."""
        if depth >= MAX_DEPTH:
            return f"`{str(data)[:100]}`\n"

        if isinstance(data, dict):
            lines = []
            for i, (k, v) in enumerate(data.items()):
                if i >= MAX_KEYS:
                    lines.append(f"\n*…{len(data) - MAX_KEYS} more keys*\n")
                    break
                if isinstance(v, (dict, list)):
                    indent = "#" * (depth + 3)
                    lines.append(f"\n{indent} {k}\n\n{self._render_data(v, depth+1)}")
                else:
                    lines.append(f"- **{k}**: {v}")
            return "\n".join(lines) + "\n"

        if isinstance(data, list):
            if not data:
                return "_empty list_\n"
            lines = []
            for i, item in enumerate(data[:MAX_KEYS]):
                if isinstance(item, (dict, list)):
                    lines.append(self._render_data(item, depth+1))
                else:
                    lines.append(f"- {item}")
            if len(data) > MAX_KEYS:
                lines.append(f"\n*…{len(data) - MAX_KEYS} more items*")
            return "\n".join(lines) + "\n"

        return f"{data}\n"
