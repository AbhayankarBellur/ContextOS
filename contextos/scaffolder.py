"""
ContextOS scaffolder.py — Vault template scaffolding and validation.

Creates structured vault directories from templates, interpolates variables,
and validates existing vaults for frontmatter compliance.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

BUILTIN_TEMPLATES = {
    "default":      "Minimal 5-folder vault for any project type",
    "microservice": "Service-focused: api, domain, decisions, runbooks",
    "api-first":    "API-first: api design, schemas, endpoints, changelogs",
}

REQUIRED_FRONTMATTER = {"project", "type", "status"}
VALID_TYPES = {"architecture", "adr", "domain", "workflow", "product", "context", "note"}
VALID_STATUSES = {"draft", "approved", "deprecated"}


def list_templates() -> dict[str, str]:
    """Return available template names and descriptions."""
    result = dict(BUILTIN_TEMPLATES)
    # Scan user templates directory
    user_templates = Path.home() / ".contextos" / "templates"
    if user_templates.exists():
        for d in user_templates.iterdir():
            if d.is_dir():
                meta_file = d / "template.yaml"
                desc = "Custom template"
                if meta_file.exists():
                    try:
                        import yaml
                        meta = yaml.safe_load(meta_file.read_text())
                        desc = meta.get("description", desc)
                    except Exception:
                        pass
                result[d.name] = desc
    return result


def scaffold_vault(
    target_path: Path,
    template_name: str = "default",
    variables: Optional[dict] = None,
) -> list[Path]:
    """
    Create vault directory structure from a template.
    Interpolates {{variable}} placeholders in file content.
    Returns list of created files.
    """
    target_path = Path(target_path)
    variables = variables or {}
    variables.setdefault("date", time.strftime("%Y-%m-%d"))

    # Find template directory
    template_dir = TEMPLATES_DIR / template_name
    if not template_dir.exists():
        # Try user templates
        user_template = Path.home() / ".contextos" / "templates" / template_name
        if user_template.exists():
            template_dir = user_template
        else:
            raise ValueError(
                f"Template '{template_name}' not found. "
                f"Available: {', '.join(list_templates().keys())}"
            )

    created_files = []

    for src_file in sorted(template_dir.rglob("*.md")):
        # Compute relative path
        rel = src_file.relative_to(template_dir)
        dst_file = target_path / rel

        # Skip if already exists
        if dst_file.exists():
            logger.debug("Skipping existing file: %s", dst_file)
            continue

        # Read and interpolate
        content = src_file.read_text(encoding="utf-8")
        content = _interpolate(content, variables)

        # Write
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        dst_file.write_text(content, encoding="utf-8")
        created_files.append(dst_file)
        logger.debug("Created: %s", dst_file)

    logger.info("Scaffolded %d files from template '%s' to %s",
                len(created_files), template_name, target_path)
    return created_files


def _interpolate(content: str, variables: dict) -> str:
    """Replace {{variable}} placeholders with values."""
    for key, value in variables.items():
        content = content.replace("{{" + key + "}}", str(value))
    return content


def validate_vault(vault_path: Path) -> dict:
    """
    Validate all Markdown files in a vault for frontmatter compliance.
    Returns {valid: int, warnings: list, errors: list}.
    """
    import frontmatter as fm_lib

    vault_path = Path(vault_path)
    errors = []
    warnings = []
    valid = 0

    for md_file in sorted(vault_path.rglob("*.md")):
        if any(p.startswith(".") for p in md_file.parts):
            continue

        try:
            post = fm_lib.loads(md_file.read_text(encoding="utf-8"))
            meta = post.metadata
        except Exception as exc:
            errors.append({"file": str(md_file), "issue": f"Parse error: {exc}"})
            continue

        file_str = str(md_file.relative_to(vault_path))

        # Check required fields
        missing = REQUIRED_FRONTMATTER - set(meta.keys())
        if missing:
            errors.append({"file": file_str, "issue": f"Missing required fields: {missing}"})
            continue

        # Validate type
        doc_type = str(meta.get("type", "")).lower()
        if doc_type not in VALID_TYPES:
            warnings.append({"file": file_str, "issue": f"Unknown type '{doc_type}'"})

        # Validate status
        status = str(meta.get("status", "")).lower()
        if status not in VALID_STATUSES:
            warnings.append({"file": file_str, "issue": f"Unknown status '{status}'"})

        # Warn on missing recommended fields
        if not meta.get("updated_at"):
            warnings.append({"file": file_str, "issue": "Missing 'updated_at'"})
        if not meta.get("tags"):
            warnings.append({"file": file_str, "issue": "Missing 'tags'"})

        valid += 1

    return {
        "valid":    valid,
        "warnings": warnings,
        "errors":   errors,
        "total":    valid + len(errors),
    }
