---
project: my-project
type: context
status: approved
owner: engineering
updated_at: 2026-06-03
tags:
  - sprint
  - current
---

# Current Sprint — Sprint 12 (June 2–13, 2026)

## Sprint Goal

Implement booking cancellation with full refund processing. Add SMS notifications for booking confirmation and cancellation.

## Active Tasks

- [ ] `BOOK-145` — Implement `DELETE /bookings/{id}` endpoint with policy check
- [ ] `BOOK-146` — Stripe refund integration in PaymentService
- [ ] `BOOK-147` — Cancellation email template
- [ ] `BOOK-148` — SMS notification via Twilio (confirmation + cancellation)
- [ ] `BOOK-149` — Add cancellation_reason field to bookings table (migration)

## Completed This Sprint

- [x] `BOOK-140` — Exponential backoff for payment retries
- [x] `BOOK-141` — Slot locking transaction with 10-minute expiry
- [x] `BOOK-142` — BookingCreated domain event

## Known Issues / Blockers

- Stripe webhook signature validation failing in staging — `BOOK-143` in progress
- Redis connection pooling needs tuning for load test results (P99 > 500ms)

## Architecture Decisions in Flight

- Evaluating whether to use Stripe's built-in retry logic vs our own exponential backoff
- Decision needed by June 10 before `BOOK-146` implementation

## Tech Debt

- Booking service `create_booking()` is 180 lines — needs refactoring after sprint
- Missing integration tests for payment failure paths
