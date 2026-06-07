# AICF — Agent Intelligence Context Format v1.0

**Published by the ContextOS project**  
**Reference implementation:** [contextos-vault](https://pypi.org/project/contextos-vault/)  
**Status:** Draft — open for community feedback

---

## Overview

AICF defines a minimal, open standard for storing and exchanging AI coding agent context.
A vault is a directory of plain Markdown files with YAML frontmatter.
Any tool can read a vault without ContextOS installed.

---

## Vault Structure

```
<project-root>/
  product/         # Vision, requirements, roadmap
  architecture/    # System design, tech stack, API surface
  domain/          # Domain models — one file per entity
  decisions/       # Architecture Decision Records (ADRs)
  workflows/       # Process flows and procedures
  context/         # Current sprint, backlog, active state
```

---

## Document Format

Every file is Markdown with YAML frontmatter:

```
---
<frontmatter>
---

# Document Title

Content...
```

---

## Required Frontmatter Fields

| Field | Type | Description |
|---|---|---|
| `project` | string | Project identifier |
| `type` | enum | See Document Types below |
| `status` | enum | `draft` \| `approved` \| `deprecated` |

---

## Recommended Frontmatter Fields

| Field | Type | Description |
|---|---|---|
| `updated_at` | date (YYYY-MM-DD) | Last update |
| `owner` | string | Team or person responsible |
| `tags` | string list | Searchable labels |
| `domain` | string | Business domain (e.g. payment, booking) |

---

## Document Types

| Type | Purpose |
|---|---|
| `architecture` | System design, tech stack, component overview |
| `adr` | Architecture Decision Record — a single decision with context and consequences |
| `domain` | Domain model — entities, relationships, business rules |
| `workflow` | Step-by-step process or procedure |
| `product` | Product vision, requirements, roadmap |
| `context` | Current state — sprint, backlog, active decisions |
| `note` | Unclassified — meeting notes, scratch, etc. |

---

## ADR Format

ADRs follow the standard lightweight template:

```markdown
---
project: my-project
type: adr
status: approved
updated_at: 2026-01-15
tags: [database, postgresql]
---

# ADR-001: Use PostgreSQL as Primary Database

## Status
Approved

## Context
[Why this decision was needed]

## Decision
[What was decided]

## Consequences
**Positive:** [benefits]
**Negative:** [tradeoffs]

## Alternatives Considered
- Option A: rejected because...
```

---

## Example: Minimal Valid Vault Document

```markdown
---
project: my-service
type: architecture
status: approved
updated_at: 2026-06-01
tags:
  - backend
  - api
---

# Backend Architecture

## Overview

FastAPI service backed by PostgreSQL. Three layers: API, service, repository.

## Tech Stack

- API: FastAPI 0.111
- Database: PostgreSQL 16
- ORM: SQLAlchemy 2.x
```

---

## Compatibility

Any tool that can read Markdown files can read an AICF vault:

- No special software required to view
- Editable with any text editor
- Version-controllable with git
- Indexable with ContextOS for agent retrieval

---

## Extending the Format

Additional frontmatter fields are allowed and ignored by tools that don't understand them.
The required fields (`project`, `type`, `status`) are the only guaranteed contract.

---

## User Memory Format

User memory fragments extend AICF with a cross-app user memory layer:

```json
{
  "id": "mem_abc123",
  "user_id": "alice@example.com",
  "content": "Prefers async patterns over sync for I/O-bound operations",
  "type": "preference",
  "importance": 4,
  "source_client": "cursor",
  "project": null,
  "created_at": "2026-06-01T10:00:00Z",
  "active": true,
  "superseded_by_id": null
}
```

Stored in `.contextos/memory/<user_id>.jsonl` — one fragment per line, append-only.

---

## Versioning

This is AICF v1.0. Breaking changes require a major version bump.
Additive changes (new optional fields, new document types) are minor versions.

---

*Open standard. No license required. Implement freely.*  
*Reference: https://github.com/AbhayankarBellur/ContextOS*
