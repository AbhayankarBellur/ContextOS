---
project: my-project
type: adr
status: approved
owner: engineering
updated_at: 2026-05-20
tags:
  - events
  - architecture
  - decisions
---

# ADR-002: Use Domain Events for Booking Lifecycle

## Status

Approved

## Context

The booking lifecycle has multiple side effects: send confirmation email, charge payment, notify provider, update analytics. Coupling these into the booking service creates a god class.

## Decision

Use domain events (BookingCreated, BookingConfirmed, BookingCancelled, BookingCompleted) dispatched via Celery task queue. Each side effect is a separate Celery task subscribed to the relevant event.

## Consequences

**Positive:**
- Booking service stays focused — no knowledge of email, payment, or analytics
- Each task is independently retryable
- Easy to add new side effects without modifying core booking logic
- Full audit trail in the event log

**Negative:**
- Eventual consistency — confirmation email arrives slightly after booking, not instantly
- Requires Celery + Redis infrastructure
- Harder to debug distributed failures

## Event Schema

All events carry: `event_type`, `booking_id`, `customer_id`, `timestamp`, `payload`.
