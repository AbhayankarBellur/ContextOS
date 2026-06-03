"""
ContextOS connectors/openapi.py — OpenAPI/Swagger spec connector.

Converts an OpenAPI 3.x or Swagger 2.x spec (JSON or YAML) into structured
Markdown vault documents. Each endpoint group becomes one architecture doc.
Agents can then query "how does the payments API work" and get structured answers.

Usage:
  context pull openapi --source ./api/openapi.yaml
  context pull openapi --source https://petstore3.swagger.io/api/v3/openapi.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from contextos.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)


class OpenAPIConnector(BaseConnector):
    """Convert OpenAPI spec into indexed architecture docs."""

    name        = "openapi"
    description = "Convert OpenAPI/Swagger spec into structured vault architecture docs"

    def __init__(self, project: str, config: Optional[dict] = None):
        super().__init__(project, config)
        self.source = self.config.get("source", "")  # file path or URL

    def fetch(self) -> list[ConnectorResult]:
        if not self.source:
            raise ValueError("openapi connector requires 'source' config (file path or URL)")

        spec = self._load_spec()
        if not spec:
            return []

        results = []

        # One overview doc
        results.append(self._make_overview(spec))

        # Group endpoints by tag
        tag_groups = self._group_by_tag(spec)
        for tag, endpoints in tag_groups.items():
            results.append(self._make_tag_doc(spec, tag, endpoints))

        # Schemas doc
        schemas_doc = self._make_schemas_doc(spec)
        if schemas_doc:
            results.append(schemas_doc)

        logger.info("OpenAPI: %d docs from %s", len(results), self.source)
        return results

    # ------------------------------------------------------------------
    # Spec loading
    # ------------------------------------------------------------------

    def _load_spec(self) -> Optional[dict]:
        source = str(self.source)

        if source.startswith("http://") or source.startswith("https://"):
            return self._load_url(source)

        path = Path(source)
        if not path.exists():
            logger.error("OpenAPI spec not found: %s", path)
            return None

        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() in (".yaml", ".yml"):
                import yaml
                return yaml.safe_load(text)
            return json.loads(text)
        except Exception as exc:
            logger.error("Failed to parse spec: %s", exc)
            return None

    def _load_url(self, url: str) -> Optional[dict]:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=15) as resp:
                text = resp.read().decode("utf-8")
            if url.endswith((".yaml", ".yml")):
                import yaml
                return yaml.safe_load(text)
            return json.loads(text)
        except Exception as exc:
            logger.error("Failed to fetch spec from URL: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Document builders
    # ------------------------------------------------------------------

    def _api_title(self, spec: dict) -> str:
        return spec.get("info", {}).get("title", "API")

    def _api_version(self, spec: dict) -> str:
        return spec.get("info", {}).get("version", "unknown")

    def _make_overview(self, spec: dict) -> ConnectorResult:
        info    = spec.get("info", {})
        title   = info.get("title", "API")
        version = info.get("version", "")
        desc    = info.get("description", "")

        servers = spec.get("servers", [])
        server_urls = [s.get("url", "") for s in servers[:3]]

        paths = spec.get("paths", {})
        total_endpoints = sum(
            len([m for m in v.keys() if m in ("get","post","put","patch","delete","options")])
            for v in paths.values()
        )

        fm = self._frontmatter({
            "project":    self.project,
            "type":       "architecture",
            "domain":     "api",
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["api", "openapi", title.lower().replace(" ","-")],
        })

        content = f"{fm}\n\n# {title} — API Overview\n\n"
        if desc:
            content += f"{desc}\n\n"
        content += f"**Version:** {version}  \n"
        content += f"**Endpoints:** {total_endpoints}  \n"
        if server_urls:
            content += f"**Servers:** {', '.join(server_urls)}  \n"
        content += "\n## Endpoint Groups\n\n"

        tag_groups = self._group_by_tag(spec)
        for tag, eps in sorted(tag_groups.items()):
            content += f"- **{tag}** — {len(eps)} endpoint(s)\n"

        return ConnectorResult(
            filename  = "api-overview.md",
            content   = content,
            title     = f"{title} — API Overview",
            doc_type  = "architecture",
            domain    = "api",
        )

    def _group_by_tag(self, spec: dict) -> dict[str, list]:
        groups: dict[str, list] = {}
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, op in methods.items():
                if method not in ("get","post","put","patch","delete","options"):
                    continue
                tags = op.get("tags", ["default"])
                for tag in tags:
                    groups.setdefault(tag, []).append({
                        "method": method.upper(),
                        "path":   path,
                        "op":     op,
                    })
        return groups

    def _make_tag_doc(self, spec: dict, tag: str, endpoints: list) -> ConnectorResult:
        slug = tag.lower().replace(" ", "-")
        fm = self._frontmatter({
            "project":    self.project,
            "type":       "architecture",
            "domain":     slug,
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["api", "openapi", slug],
        })

        content = f"{fm}\n\n# API — {tag}\n\n"
        content += f"{len(endpoints)} endpoint(s) in this group.\n\n"

        for ep in sorted(endpoints, key=lambda x: x["path"]):
            op     = ep["op"]
            method = ep["method"]
            path   = ep["path"]
            summary = op.get("summary", "")
            desc    = op.get("description", "")

            content += f"## `{method} {path}`\n\n"
            if summary:
                content += f"**{summary}**\n\n"
            if desc:
                content += f"{desc}\n\n"

            # Parameters
            params = op.get("parameters", [])
            if params:
                content += "**Parameters:**\n\n"
                for p in params[:10]:
                    name     = p.get("name","")
                    location = p.get("in","")
                    required = "required" if p.get("required") else "optional"
                    ptype    = p.get("schema", {}).get("type","")
                    pdesc    = p.get("description","")
                    content += f"- `{name}` ({location}, {required}, {ptype})"
                    if pdesc:
                        content += f" — {pdesc}"
                    content += "\n"
                content += "\n"

            # Request body summary
            req_body = op.get("requestBody", {})
            if req_body:
                content += "**Request Body:** "
                content += req_body.get("description","") or "See schema"
                content += "\n\n"

            # Responses
            responses = op.get("responses", {})
            if responses:
                content += "**Responses:** "
                content += ", ".join(f"`{code}`" for code in list(responses.keys())[:5])
                content += "\n\n"

        return ConnectorResult(
            filename = f"api-{slug}.md",
            content  = content,
            title    = f"API — {tag}",
            doc_type = "architecture",
            domain   = slug,
        )

    def _make_schemas_doc(self, spec: dict) -> Optional[ConnectorResult]:
        components = spec.get("components", {})
        schemas    = components.get("schemas", {})
        if not schemas:
            # Swagger 2.x
            schemas = spec.get("definitions", {})
        if not schemas:
            return None

        fm = self._frontmatter({
            "project":    self.project,
            "type":       "domain",
            "domain":     "api-schemas",
            "status":     "approved",
            "updated_at": __import__("time").strftime("%Y-%m-%d"),
            "tags":       ["api", "schemas", "data-models"],
        })

        content = f"{fm}\n\n# API Data Schemas\n\n"
        content += f"{len(schemas)} schema(s) defined.\n\n"

        for name, schema in list(schemas.items())[:30]:
            content += f"## {name}\n\n"
            desc = schema.get("description","")
            if desc:
                content += f"{desc}\n\n"
            props = schema.get("properties", {})
            if props:
                content += "| Field | Type | Description |\n|---|---|---|\n"
                for fname, fdef in list(props.items())[:15]:
                    ftype = fdef.get("type","") or fdef.get("$ref","").split("/")[-1]
                    fdesc = fdef.get("description","")
                    content += f"| `{fname}` | {ftype} | {fdesc} |\n"
                content += "\n"

        return ConnectorResult(
            filename = "api-schemas.md",
            content  = content,
            title    = "API Data Schemas",
            doc_type = "domain",
            domain   = "api-schemas",
        )
