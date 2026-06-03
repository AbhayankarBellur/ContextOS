---
project: contextos
type: adr
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - security
  - local-first
  - decisions
---

# ADR-003: 100% Local — Zero Network Dependency

## Status
Approved — Non-negotiable constraint

## Context
Developers working on proprietary codebases cannot send code or architecture to cloud services. Privacy and air-gap requirements are common.

## Decision
ContextOS makes zero outbound network calls at runtime. No telemetry, no update checks, no cloud embedding APIs.

## Enforcement Rules
1. `api.py` must set `host='127.0.0.1'` unconditionally
2. Embedding model uses `local_files_only=True` after first download
3. LanceDB uses local directory path only — no cloud URI
4. No `import requests` usage at runtime (only allowed in test/dev tooling)
5. No auto-update mechanism

## Consequence
First `context index` run requires internet to download the ~130MB model. All subsequent operations are fully offline. This is the only network call ContextOS ever makes.
