# recallist-server

Recallist is a lightweight Model Context Protocol (MCP) server that gives GPT-based agents a simple, persistent, per-user item list. Agents can add notes, mark them resolved, fetch a random unresolved item, and list everything — useful for micro-learning, spaced repetition, reminders, and lightweight personal memory.

## Key Features
- Single FastAPI app mounted as two sub-APIs: `/api/*` (main) and `/gpt/*` (GPT-focused)
- `/api/*` uses standard REST verbs; `/gpt/*` is GET-only for simpler GPT tool usage
- Per-user storage in DynamoDB with case-insensitive keys, preserving original casing for display
- Auth split by sub-API:
  - `/api/*`: Cognito JWT authorizer (Authorization: Bearer …)
  - `/gpt/*`: Lightweight Lambda REQUEST authorizer that only checks token presence
- Infrastructure-as-Code with Terraform using a single HTTP API Gateway (v2)

## High-level Architecture
- FastAPI application in `lambda/`, adapted for Lambda with `mangum`.
- Two sub-apps mounted under one root app:
  - `/api` → for web app usage (JWT auth), with docs at `/api/docs` and schema at `/api/openapi.json` (public)
  - `/gpt` → for GPT integrations (GET-only + token auth), with docs at `/gpt/docs` and schema at `/gpt/openapi.json` (public)
- Custom Lambda REQUEST authorizer in `lambda_authorizer/` accepts any non-empty `Authorization` header and uses its value as `user_id`.
- Data stored in DynamoDB:
  - Table: `recallist_items` (partition key: `user_id`, sort key: `item` [normalized lowercase])
  - Table: `recallist_api_keys` (currently unused by authorizer; kept for possible future mapping)
- Terraform definitions in `infra/main.tf` provision IAM, DynamoDB, HTTP API, Cognito, and Lambdas.

## Data Model (DynamoDB)
Items are stored per user with a normalized item key for case-insensitive behavior.
- user_id: string (PK)
- item: string (SK, normalized lowercase of the item text)
- display_item: string (original user-provided text, preserved for display)
- status: "NEW" | "RESOLVED"
- createdDate: ISO8601 UTC string
- resolutionDate: ISO8601 UTC string (when resolved)

## API Overview
All endpoints require authorization except the documentation endpoints.

Main API (under `/api`):
- GET `/api/item/random` → 200 with a random unresolved item; 404 if none
- GET `/api/items` → 200 with all items (resolved and unresolved)
- GET `/api/item/{item}` → 200 with a single item; 404 if not found (case-insensitive)
- POST `/api/item` → 201 creates a new item `{ item: string }`; 409 if duplicate; 400 if empty
- PATCH `/api/item/{item}` → 200 marks as RESOLVED and sets `resolutionDate`; 404 if not found
- DELETE `/api/item/{item}` → 204 on success; 404 if not found

GPT API (under `/gpt`) — GET-only for simple tool calls:
- GET `/gpt/item/random` → fetch random unresolved
- GET `/gpt/items` → list all
- GET `/gpt/item/{item}` → get single
- GET `/gpt/item/add?item=...` → create new item
- GET `/gpt/item/{item}/resolve` → mark as resolved
- GET `/gpt/item/{item}/delete` → delete item (204 on success)

Docs and schemas (public):
- `/api/docs`, `/api/openapi.json`
- `/gpt/docs`, `/gpt/openapi.json`

## Authorization
- `/api/*` uses a JWT authorizer configured with Cognito. The app extracts the `sub` claim as `user_id`.
- `/gpt/*` uses a simple Lambda REQUEST authorizer that only checks the presence of the `Authorization` header and uses its value as `user_id` (no JWT validation).

## Environment Variables
- `ITEM_TABLE` (default: `recallist_items`)
- `LOG_LEVEL` (default: `INFO`)
- `ENVIRONMENT` (default: `development`; affects log formatting)

## Local Development
Although designed for Lambda, you can run FastAPI locally for quick testing:
- Install requirements from `lambda/requirements.txt`.
- Set AWS credentials pointing to a test account or local DynamoDB (adjust resource if needed).
- Run the app (example):
  ```bash
  uvicorn lambda.main:app --reload
  ```
  Note: In Lambda, the handler is created via `Mangum(app)`.

## Deployment (Terraform)
The Terraform stack in `infra/main.tf` provisions the AWS resources (IAM, DynamoDB, HTTP API, Cognito, and Lambda wiring). Typical flow:
- Ensure the Lambda deployment ZIP contains the `lambda/` sources and dependencies.
- `terraform init`
- `terraform plan`
- `terraform apply`