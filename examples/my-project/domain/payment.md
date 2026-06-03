---
project: my-project
type: domain
domain: payment
status: approved
owner: engineering
updated_at: 2026-06-01
tags:
  - payment
  - domain-model
  - stripe
---

# Payment Domain Model

## Overview

Payment processing wraps the Stripe API. All payment state is stored locally in the payments table. Stripe is the source of truth for charge status.

## Payment Entity

**Fields:**
- `id`: UUID
- `booking_id`: FK to Booking
- `amount`: integer (cents)
- `currency`: string (default: USD)
- `status`: enum — pending | processing | succeeded | failed | refunded | partially_refunded
- `stripe_payment_intent_id`: string
- `created_at`: timestamp
- `updated_at`: timestamp

## Payment Retry Logic

Payment retries use exponential backoff to handle transient failures:

1. First attempt: immediate
2. Retry 1: after 5 seconds
3. Retry 2: after 25 seconds
4. Retry 3: after 125 seconds
5. Give up: mark as failed, notify customer

## Refund Policy

- Full refund: cancellation > 24 hours before slot
- 50% refund: cancellation within 24 hours
- No refund: no-show or cancellation within 1 hour
- Processing time: 5-10 business days for card refunds

## Idempotency

All Stripe calls use idempotency keys derived from `booking_id + attempt_number`. This prevents double-charging on network retries.
