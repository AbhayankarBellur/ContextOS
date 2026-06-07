"""
ContextOS ui.py — Shared UI components and theme.
Premium terminal experience matching Claude Code / Vercel CLI quality.
Uses Rich exclusively — no manual ANSI sequences.
"""
from __future__ import annotations
import shutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.theme import Theme
from rich.style import Style

VERSION = "1.5.0"

# ---------------------------------------------------------------------------
# Theme — Cyan primary, Blue secondary, professional palette
# ---------------------------------------------------------------------------
THEME = Theme({
    "brand":     "bold cyan",
    "brand.sub": "bold blue",
    "success":   "bold green",
    "warning":   "bold yellow",
    "error":     "bold red",
    "muted":     "dim white",
    "info":      "cyan",
    "heading":   "bold white",
    "score.hi":  "bold green",
    "score.mid": "bold yellow",
    "score.lo":  "bold red",
    "type.architecture": "cyan",
    "type.adr":          "magenta",
    "type.domain":       "blue",
    "type.workflow":     "green",
    "type.product":      "yellow",
    "type.context":      "bold cyan",
    "type.note":         "dim white",
})

console = Console(theme=THEME, highlight=False)

# ---------------------------------------------------------------------------
# Nerd font detection
# ---------------------------------------------------------------------------
def _has_nerd_fonts() -> bool:
    """Best-effort check: look for common nerd font env hints."""
    import os
    font_hint = os.environ.get("TERM_PROGRAM", "") + os.environ.get("COLORTERM", "")
    return any(x in font_hint.lower() for x in ("iterm", "warp", "kitty", "alacritty"))

USE_NERD = _has_nerd_fonts()

# Icon set — ASCII fallback if no nerd font
ICONS = {
    "success": "✓" ,
    "error":   "✗",
    "warning": "⚠",
    "info":    "ℹ",
    "spin":    "⟳",
    "bullet":  "•",
    "arrow":   "→",
    "index":   "◈",
    "graph":   "⬡",
    "vault":   "⬛",
    "server":  "◎",
    "token":   "⬡",
    "memory":  "▣",
}

# ---------------------------------------------------------------------------
# ASCII Logo — shown only on first launch, doctor, about
# ---------------------------------------------------------------------------
LOGO = r"""
  _____            _            _    ___  ____
 / ____|          | |          | |  / _ \/ ___|
| |     ___  _ __ | |_ _____  _| |_| | | \___ \
| |    / _ \| '_ \| __/ _ \ \/ / __| | | |___) |
| |___| (_) | | | | ||  __/>  <| |_| |_| |___) |
 \_____\___/|_| |_|\__\___/_/\_\\__|\___/|____/
"""

# ---------------------------------------------------------------------------
# Brand header — compact, used on most commands
# ---------------------------------------------------------------------------
def brand_rule(subtitle: str = ""):
    """Print a branded horizontal rule."""
    label = "[bold cyan]Context[/bold cyan][bold blue]OS[/bold blue]"
    if subtitle:
        label += f"  [dim]{subtitle}[/dim]"
    console.print(Rule(label, style="cyan"))

def print_logo():
    """Print full ASCII logo — first launch / doctor / about only."""
    console.print(f"[bold cyan]{LOGO}[/bold cyan]")
    console.print(f"[dim]  v{VERSION}  —  Local-first knowledge OS for AI coding agents[/dim]\n")

# ---------------------------------------------------------------------------
# Status line helpers
# ---------------------------------------------------------------------------
def ok(msg: str):
    console.print(f"[success]{ICONS['success']}[/success] {msg}")

def warn(msg: str):
    console.print(f"[warning]{ICONS['warning']}[/warning]  {msg}")

def err(msg: str):
    console.print(f"[error]{ICONS['error']}[/error] {msg}")

def info(msg: str):
    console.print(f"[info]{ICONS['info']}[/info]  {msg}")

def next_action(cmd: str, description: str = ""):
    """Show a 'next step' hint after a command."""
    console.print()
    console.print(Rule("[dim]Next[/dim]", style="dim"))
    if description:
        console.print(f"  [dim]{description}[/dim]")
    console.print(f"  [bold cyan]{cmd}[/bold cyan]")

# ---------------------------------------------------------------------------
# Score colouring
# ---------------------------------------------------------------------------
def score_style(score: float) -> str:
    if score >= 0.80: return "score.hi"
    if score >= 0.60: return "score.mid"
    return "score.lo"

def type_style(doc_type: str) -> str:
    key = f"type.{doc_type}"
    try:
        THEME.resolve(key)
        return key
    except Exception:
        return "info"

# ---------------------------------------------------------------------------
# Error panel — actionable, never raw tracebacks
# ---------------------------------------------------------------------------
def error_panel(title: str, message: str, hint: str = ""):
    body = f"[error]{message}[/error]"
    if hint:
        body += f"\n\n[dim]{ICONS['arrow']} {hint}[/dim]"
    console.print(Panel(body, title=f"[error]{ICONS['error']} {title}[/error]",
                        border_style="red", padding=(0, 2)))

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
def empty_state(message: str, suggestion: str):
    console.print(Panel(
        f"[dim]{message}[/dim]\n\n[dim]Run:[/dim]\n  [bold cyan]{suggestion}[/bold cyan]",
        border_style="dim", padding=(0, 2)
    ))
