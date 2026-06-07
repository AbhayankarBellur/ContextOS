"""
ContextOS ingestors/pdf.py — PDF text extraction via pymupdf (fitz).

Extracts text page-by-page, preserving structure.
Each page becomes a section: ## Page N
Metadata extracted from PDF info dict when available.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from contextos.ingestors import register


@register(".pdf", "pymupdf")
def extract_pdf(path: Path) -> str:
    import fitz  # pymupdf

    doc = fitz.open(str(path))
    info = doc.metadata or {}

    title = (
        info.get("title", "").strip()
        or path.stem.replace("-", " ").replace("_", " ").title()
    )
    author  = info.get("author", "").strip() or None
    subject = info.get("subject", "").strip() or None
    pages   = doc.page_count

    # Build frontmatter
    fm_lines = [
        "---",
        f"project: unknown",          # caller fills in from registry
        f"type: note",
        f"status: draft",
        f"source: pdf",
        f"updated_at: {time.strftime('%Y-%m-%d')}",
        f"tags:",
        f"  - pdf",
        f"  - imported",
    ]
    if author:
        fm_lines.append(f"owner: {author}")
    fm_lines += [
        f"pages: {pages}",
        "---",
        "",
        f"# {title}",
        "",
    ]

    if subject:
        fm_lines += [f"*{subject}*", ""]

    # Extract text per page
    sections = []
    for page_num in range(pages):
        page  = doc[page_num]
        text  = page.get_text("text").strip()
        if not text:
            # Attempt OCR for scanned pages (requires pytesseract + tesseract)
            try:
                import pytesseract
                from PIL import Image
                import io
                pix   = page.get_pixmap(dpi=150)
                img   = Image.open(io.BytesIO(pix.tobytes("png")))
                text  = pytesseract.image_to_string(img).strip()
                if text:
                    sections.append(f"## Page {page_num + 1} (OCR)\n\n{text}")
                    continue
            except ImportError:
                pass  # tesseract not installed — skip this page silently
            except Exception:
                pass
            continue
        sections.append(f"## Page {page_num + 1}\n\n{text}")

    doc.close()

    if not sections:
        fm_lines.append("*No extractable text found in this PDF.*")
        return "\n".join(fm_lines)

    return "\n".join(fm_lines) + "\n\n" + "\n\n".join(sections)
