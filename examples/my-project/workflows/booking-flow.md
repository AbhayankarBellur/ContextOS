---
project: my-project
type: workflow
domain: booking
status: approved
owner: engineering
updated_at: 2026-06-01
tags:
  - booking
  - workflow
  - payment
---

# Booking Flow

## Overview

End-to-end flow from customer selecting a slot to confirmed booking.

## Steps

### 1. Customer Selects Slot

- Customer browses available slots via `GET /slots?date=&provider=`
- Frontend displays available slots (is_available = true)

### 2. Slot Lock (Optimistic)

- Customer submits booking: `POST /bookings`
- System checks slot availability in a transaction
- If available: set `slot.is_available = false`, create booking with status `pending`
- If unavailable: return 409 Conflict
- Lock expires after 10 minutes if payment is not completed

### 3. Payment Processing

- Frontend calls `POST /payments` with booking_id
- Payment service creates Stripe PaymentIntent
- Customer completes payment on frontend (Stripe Elements)
- Stripe sends webhook: `payment_intent.succeeded`

### 4. Booking Confirmation

- Webhook handler confirms booking: status → `confirmed`
- Emits `BookingConfirmed` event
- Celery tasks: send confirmation email, notify provider

### 5. Failure Handling

- Payment fails: booking stays `pending`, retry up to 3 times
- All retries fail: release slot lock, booking → `failed`, notify customer
- Webhook timeout: background job checks pending bookings older than 15 min

## Cancellation Sub-flow

1. Customer calls `DELETE /bookings/{id}`
2. System checks cancellation policy (24hr window)
3. If eligible: booking → `cancelled`, emit `BookingCancelled`
4. Celery task: process refund via Stripe, send cancellation email
