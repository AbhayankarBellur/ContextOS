---
project: my-project
type: adr
status: approved
owner: engineering
updated_at: 2026-05-15
tags:
  - database
  - postgresql
  - decisions
---

# ADR-001: Use PostgreSQL as Primary Database

## Status

Approved

## Context

We need a relational database for the booking platform. Key requirements:
- ACID transactions for booking slot locking (prevent double-booking)
- Strong consistency for payment records
- Good ORM support for Python (SQLAlchemy)
- Managed hosting options available (Supabase, RDS)

## Decision

Use PostgreSQL 16 as the primary database.

## Consequences

**Positive:**
- Full ACID compliance — critical for slot locking and payment records
- Excellent SQLAlchemy 2.x support
- Rich JSON support for flexible metadata storage
- Strong community and ecosystem

**Negative:**
- Not horizontally scalable by default (acceptable at current scale)
- Requires connection pooling for high concurrency (use PgBouncer in production)

## Alternatives Considered

- MySQL: rejected — weaker JSON support, row-level locking less granular
- MongoDB: rejected — ACID transactions added complexity, no natural fit for relational booking data
- SQLite: rejected — not suitable for multi-process production workload
