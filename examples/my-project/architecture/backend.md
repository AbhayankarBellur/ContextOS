---
project: my-project
type: architecture
domain: booking
status: approved
owner: engineering
updated_at: 2026-06-01
tags:
  - backend
  - api
  - booking
---

# Backend Architecture

## Overview

The backend is a Python FastAPI monolith with a PostgreSQL database. Services are organised by domain: booking, payment, auth, and notifications.

## Tech Stack

- **API Framework**: FastAPI 0.111
- **Database**: PostgreSQL 16 with SQLAlchemy 2.x ORM
- **Task Queue**: Celery + Redis for async tasks
- **Authentication**: JWT with 24-hour expiry

## Domain Services

### Booking Service

Handles all booking lifecycle operations.

- Create booking: validates availability, locks slot, creates booking record
- Cancel booking: checks cancellation policy, triggers refund if applicable
- Reschedule: atomic cancel + rebook in a single transaction

### Payment Service

Wraps Stripe for all payment operations.

- Charge on booking confirmation
- Refund on cancellation within policy window
- Payment retries use exponential backoff: 5s, 25s, 125s

### Auth Service

- Registration and login via email/password
- OAuth2 via Google and GitHub
- Token refresh every 24 hours

## Database Schema (Key Tables)

- `bookings`: id, customer_id, slot_id, status, created_at, cancelled_at
- `slots`: id, provider_id, start_time, end_time, is_available
- `payments`: id, booking_id, amount, currency, status, stripe_id
- `customers`: id, email, name, phone, created_at
