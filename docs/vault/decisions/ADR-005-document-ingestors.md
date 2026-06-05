---
project: contextos
type: adr
status: approved
owner: core-team
updated_at: 2026-06-04
tags:
  - ingestors
  - pdf
  - docx
  - pptx
  - decisions
---

# ADR-005: Pluggable Document Ingestor Pipeline

## Status
Approved

## Context
ContextOS was Markdown-only. Enterprise teams store knowledge in PDFs (architecture specs, compliance docs), Word documents (meeting notes, requirements), and PowerPoint decks (design reviews, onboarding). Blocking on format is a hard adoption blocker.

## Decision
Implement a pluggable ingestor pipeline in `contextos/ingestors/`. Each ingestor converts a binary format to Markdown with YAML frontmatter, then feeds the existing chunker and embedder unchanged.

### Supported Formats
| Format | Library | Strategy |
|---|---|---|
| `.pdf` | pymupdf (fitz) | Page-by-page text extraction, `## Page N` sections |
| `.docx` | python-docx | Paragraph/heading/table → Markdown, inline bold/italic |
| `.pptx` | python-pptx | Slide → `## Slide N: {title}`, body text, speaker notes |

### Architecture
```
scan_vault() detects extension
  .md  → parse_document() (existing)
  .pdf/.docx/.pptx → _ingest_document() → ingestors.ingest(path)
    → ingestor returns Markdown string with frontmatter
    → parse_document() receives Markdown as if native
```

### Registration
```python
@register(".pdf", "pymupdf")
def extract_pdf(path: Path) -> str: ...
```

## Consequences
**Positive:**
- Existing chunker, embedder, store unchanged — zero ripple effect
- Graceful degradation: missing library logs warning and skips file
- New formats added by dropping a file in ingestors/ and using @register
- PDF/DOCX/PPTX files appear in `context search` results like any vault doc

**Negative:**
- Text extraction quality varies by document complexity (scanned PDFs not supported)
- Adds ~15MB dependencies (pymupdf, python-docx, python-pptx)
- Generated Markdown may need manual cleanup for complex layouts

## Non-Goals
- OCR for scanned PDFs (v1.5 — requires tesseract)
- Excel/CSV (v1.5 — tabular data needs different chunking strategy)
- Email/HTML (v1.5)
