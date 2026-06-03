---
project: {{project_name}}
type: domain
domain: {{domain_name}}
status: draft
owner: {{team}}
updated_at: {{date}}
tags:
  - domain
  - {{domain_name}}
---

# {{domain_name}} Domain Model

## Entities

### EntityName

**Fields:**
- `id`: UUID
- `created_at`: timestamp
- `updated_at`: timestamp

**Business Rules:**
- _Rule 1_
- _Rule 2_

## Domain Events

- `EntityCreated`
- `EntityUpdated`
- `EntityDeleted`
