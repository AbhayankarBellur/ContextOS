"""
ContextOS plugins.py — Plugin discovery and connector registry.

Scans plugin directories for third-party connectors and merges them
with built-in connectors into a unified registry.

Plugin directories (scanned in order, later overrides earlier):
  1. contextos/connectors/   — built-in connectors
  2. ~/.contextos/plugins/   — user-installed global plugins
  3. ./contextos_plugins/    — project-local plugins

A plugin is any Python file containing a class that:
  - Inherits from BaseConnector
  - Has a non-empty `name` class attribute
  - Has a `description` class attribute

Plugin installation:
  context plugin install <package>  →  pip install into ~/.contextos/plugins/
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from contextos.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

GLOBAL_PLUGIN_DIR = Path.home() / ".contextos" / "plugins"
LOCAL_PLUGIN_DIR  = Path("contextos_plugins")


@dataclass
class PluginMeta:
    name:          str
    description:   str
    cls:           type
    source:        str          # "builtin" | "global" | "local" | "package"
    config_schema: dict = field(default_factory=dict)
    version:       str  = "unknown"


def _is_valid_connector(cls) -> bool:
    """Check if a class is a valid connector (inherits BaseConnector, has name)."""
    try:
        return (
            isinstance(cls, type)
            and issubclass(cls, BaseConnector)
            and cls is not BaseConnector
            and bool(getattr(cls, "name", ""))
        )
    except Exception:
        return False


def _load_from_module(module, source: str) -> list[PluginMeta]:
    """Extract all valid connector classes from a loaded module."""
    found = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if _is_valid_connector(obj):
            found.append(PluginMeta(
                name        = obj.name,
                description = getattr(obj, "description", ""),
                cls         = obj,
                source      = source,
                version     = getattr(obj, "version", "unknown"),
            ))
    return found


def _scan_directory(plugin_dir: Path, source: str) -> list[PluginMeta]:
    """Scan a directory for .py files containing connector classes."""
    if not plugin_dir.exists():
        return []

    plugins = []
    for py_file in sorted(plugin_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec   = importlib.util.spec_from_file_location(py_file.stem, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            found  = _load_from_module(module, source)
            plugins.extend(found)
            if found:
                logger.info("Loaded %d plugin(s) from %s", len(found), py_file)
        except Exception as exc:
            logger.warning("Failed to load plugin %s: %s", py_file, exc)

    return plugins


def scan_plugins() -> list[PluginMeta]:
    """
    Discover all plugins across all plugin directories.
    Returns list of PluginMeta, in discovery order.
    """
    all_plugins: list[PluginMeta] = []

    # 1. Built-in connectors
    from contextos.connectors import CONNECTORS as builtin
    for name, cls in builtin.items():
        all_plugins.append(PluginMeta(
            name        = name,
            description = getattr(cls, "description", ""),
            cls         = cls,
            source      = "builtin",
        ))

    # 2. Global user plugins (~/.contextos/plugins/)
    all_plugins.extend(_scan_directory(GLOBAL_PLUGIN_DIR, "global"))

    # 3. Project-local plugins (./contextos_plugins/)
    all_plugins.extend(_scan_directory(LOCAL_PLUGIN_DIR, "local"))

    # 4. Installed packages with entry_point group "contextos.connectors"
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="contextos.connectors")
        for ep in eps:
            try:
                cls = ep.load()
                if _is_valid_connector(cls):
                    all_plugins.append(PluginMeta(
                        name        = cls.name,
                        description = getattr(cls, "description", ep.name),
                        cls         = cls,
                        source      = "package",
                        version     = ep.dist.version if hasattr(ep, "dist") else "unknown",
                    ))
            except Exception as exc:
                logger.warning("Failed to load entry point %s: %s", ep.name, exc)
    except Exception:
        pass

    return all_plugins


def build_registry() -> dict[str, type[BaseConnector]]:
    """
    Build the unified connector registry.
    Later entries (global > builtin, local > global) override earlier ones.
    Returns {name: ConnectorClass}.
    """
    registry: dict[str, type[BaseConnector]] = {}
    for meta in scan_plugins():
        registry[meta.name] = meta.cls
    return registry


def install_plugin(package: str, upgrade: bool = False) -> bool:
    """
    Install a plugin package into the global plugin directory.
    Uses pip to install, then scans for newly available connectors.
    Returns True on success.
    """
    GLOBAL_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(GLOBAL_PLUGIN_DIR),
        package,
    ]
    if upgrade:
        cmd.append("--upgrade")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logger.info("Plugin installed: %s", package)
            return True
        else:
            logger.error("Plugin install failed: %s", result.stderr)
            return False
    except Exception as exc:
        logger.error("Plugin install exception: %s", exc)
        return False


def list_plugins() -> list[PluginMeta]:
    """Return all discovered plugins with metadata."""
    return scan_plugins()
