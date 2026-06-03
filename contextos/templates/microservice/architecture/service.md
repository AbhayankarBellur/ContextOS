---
project: {{project_name}}
type: architecture
status: draft
owner: {{team}}
updated_at: {{date}}
tags:
  - microservice
  - architecture
---

# {{project_name}} Service Architecture

## Responsibility

_One sentence: what does this service own and what does it not own._

## API Surface

| Method | Endpoint | Description |
|---|---|---|
| GET | /health | Health check |

## Data Ownership

_What data does this service own? What data does it read from other services?_

## Events Published

- `ServiceEvent` — emitted when...

## Events Consumed

- `UpstreamEvent` — from service X, triggers...

## Dependencies

| Service | Type | Reason |
|---|---|---|
| _ServiceName_ | sync/async | _why_ |

## Runbook

_Link to runbook or describe key operational procedures._
