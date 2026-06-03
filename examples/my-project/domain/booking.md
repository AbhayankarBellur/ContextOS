---
project: my-project
type: domain
domain: booking
status: approved
owner: engineering
updated_at: 2026-06-01
tags:
  - booking
  - domain-model
---

# Booking Domain Model

## Entities

### Booking

The core aggregate root of the booking domain.

**Fields:**
- `id`: UUID primary key
- `customer_id`: FK to Customer
- `slot_id`: FK to Slot
- `status`: enum — pending | confirmed | cancelled | completed | no_show
- `created_at`: timestamp
- `confirmed_at`: timestamp (nullable)
- `cancelled_at`: timestamp (nullable)
- `cancellation_reason`: string (nullable)

**Business Rules:**
- A booking can only be cancelled if status is pending or confirmed
- Cancellations within 24 hours incur a 50% fee
- Free cancellation up to 24 hours before the slot start

### Slot

Represents an available time window for booking.

**Fields:**
- `id`: UUID
- `provider_id`: FK to Provider
- `start_time`: datetime
- `end_time`: datetime
- `is_available`: boolean
- `booking_id`: FK to Booking (nullable — set when booked)

### Customer

The person making the booking.

**Fields:**
- `id`: UUID
- `email`: unique, required
- `name`: string
- `phone`: optional

## Domain Events

- `BookingCreated` — emitted after successful slot lock
- `BookingConfirmed` — emitted after payment success
- `BookingCancelled` — emitted after cancellation, triggers refund check
- `BookingCompleted` — emitted at slot end time
