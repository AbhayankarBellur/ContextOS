"""
ContextOS symbols.py — AST-powered symbol index for Python source files.
Extracts functions, classes, and methods. Stored in .contextos/symbols/.
Rebuilt incrementally during context index.
No external dependencies beyond stdlib ast module.
"""
from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SYMBOLS_DIR_NAME = "symbols"
SYMBOL_INDEX_FILE = "index.json"

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx"}


# ---------------------------------------------------------------------------
# Python AST extraction
# ---------------------------------------------------------------------------

class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]):
        self.source_lines = source_lines
        self.symbols: list[dict] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self._class_stack.append(node.name)
        self.symbols.append({
            "name":       node.name,
            "qualified":  ".".join(self._class_stack),
            "type":       "class",
            "line_start": node.lineno,
            "line_end":   node.end_lineno or node.lineno,
            "signature":  f"class {node.name}",
            "docstring":  ast.get_docstring(node) or "",
        })
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_func(node, is_async=True)

    def _visit_func(self, node, is_async: bool):
        prefix = "async def" if is_async else "def"
        args = [a.arg for a in node.args.args]
        sig = f"{prefix} {node.name}({', '.join(args)})"
        qualified = ".".join(self._class_stack + [node.name]) if self._class_stack else node.name
        sym_type = "method" if self._class_stack else "function"
        self.symbols.append({
            "name":       node.name,
            "qualified":  qualified,
            "type":       sym_type,
            "line_start": node.lineno,
            "line_end":   node.end_lineno or node.lineno,
            "signature":  sig,
            "docstring":  ast.get_docstring(node) or "",
            "is_async":   is_async,
        })
        self.generic_visit(node)


def extract_python_symbols(filepath: Path) -> list[dict]:
    """Extract all symbols from a Python file using ast."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        visitor = _PythonVisitor(source.splitlines())
        visitor.visit(tree)
        return visitor.symbols
    except SyntaxError as exc:
        logger.debug("Syntax error in %s: %s", filepath, exc)
        return []
    except Exception as exc:
        logger.debug("Failed to parse %s: %s", filepath, exc)
        return []


# ---------------------------------------------------------------------------
# JS/TS regex fallback
# ---------------------------------------------------------------------------

_JS_FUNC_PATTERNS = [
    # function foo(
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE),
    # const foo = (
    re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(", re.MULTILINE),
    # class Foo
    re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE),
]


def extract_js_symbols(filepath: Path) -> list[dict]:
    """Regex-based symbol extraction for JS/TS files."""
    symbols = []
    try:
        lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
        for i, line in enumerate(lines, 1):
            for pattern in _JS_FUNC_PATTERNS:
                m = pattern.match(line.strip())
                if m:
                    name = m.group(1)
                    sym_type = "class" if "class" in line else "function"
                    symbols.append({
                        "name":       name,
                        "qualified":  name,
                        "type":       sym_type,
                        "line_start": i,
                        "line_end":   i,
                        "signature":  line.strip()[:120],
                        "docstring":  "",
                    })
    except Exception as exc:
        logger.debug("JS/TS extraction failed for %s: %s", filepath, exc)
    return symbols


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def extract_symbols(filepath: Path) -> list[dict]:
    """Extract symbols from any supported file type."""
    ext = filepath.suffix.lower()
    if ext == ".py":
        return extract_python_symbols(filepath)
    elif ext in (".js", ".ts", ".tsx", ".jsx"):
        return extract_js_symbols(filepath)
    return []


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def build_symbol_index(source_paths: list[Path], symbols_dir: Path) -> dict:
    """
    Walk source paths, extract symbols from all supported files,
    write to .contextos/symbols/index.json.
    Returns summary {files, symbols}.
    """
    symbols_dir.mkdir(parents=True, exist_ok=True)
    all_records: list[dict] = []
    file_count = 0

    SKIP = {".git", "__pycache__", ".contextos", "node_modules", ".venv", "venv", "dist", "build"}

    for base_path in source_paths:
        if not base_path.exists():
            continue
        for filepath in base_path.rglob("*"):
            if filepath.suffix not in SUPPORTED_EXTENSIONS:
                continue
            if any(p in SKIP or p.startswith(".") for p in filepath.parts):
                continue
            if not filepath.is_file():
                continue

            syms = extract_symbols(filepath)
            if syms:
                file_count += 1
                for s in syms:
                    all_records.append({**s, "file": str(filepath)})

    index_path = symbols_dir / SYMBOL_INDEX_FILE
    index_path.write_text(json.dumps(all_records, indent=2))
    logger.info("Symbol index: %d symbols from %d files", len(all_records), file_count)
    return {"files": file_count, "symbols": len(all_records)}


def search_symbols(
    query: str,
    symbols_dir: Path,
    sym_type: Optional[str] = None,
    file_pattern: Optional[str] = None,
    fuzzy: bool = True,
    limit: int = 20,
) -> list[dict]:
    """
    Search the symbol index by name.
    fuzzy=True: substring match (case-insensitive)
    fuzzy=False: exact match
    """
    index_path = symbols_dir / SYMBOL_INDEX_FILE
    if not index_path.exists():
        return []

    records = json.loads(index_path.read_text())
    q = query.lower()
    results = []

    for r in records:
        name = r.get("name", "").lower()
        # Name match
        if fuzzy:
            if q not in name and q not in r.get("qualified", "").lower():
                continue
        else:
            if name != q:
                continue
        # Type filter
        if sym_type and r.get("type") != sym_type:
            continue
        # File pattern filter
        if file_pattern and file_pattern not in r.get("file", ""):
            continue
        results.append(r)
        if len(results) >= limit:
            break

    # Sort: exact matches first, then by name length
    results.sort(key=lambda r: (0 if r.get("name", "").lower() == q else 1, len(r.get("name", ""))))
    return results
