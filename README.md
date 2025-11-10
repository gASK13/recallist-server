# recallist-server

Recallist is a lightweight Model Context Protocol (MCP) server that gives GPT-based agents a simple, persistent, per-user item list. Agents can add notes, mark them resolved, fetch a random unresolved item, and list everything — useful for micro-learning, spaced repetition, reminders, and lightweight personal memory.

This is in "active development" - aim is to keep this simple, but allow this to be used in any GPT as simple "itemized storage" with easy web-UI to manage.

## Key Features
- Single FastAPI app mounted as two sub-APIs: `/api/*` (main) and `/gpt/*` (GPT-focused)
- `/api/*` uses standard REST verbs; `/gpt/*` is GET-only for simpler GPT tool usage
- Per-user storage in DynamoDB with case-insensitive keys, preserving original casing for display
- Auth split by sub-API:
  - `/api/*`: Cognito JWT authorizer (Authorization: Bearer …)
  - `/gpt/*`: Lightweight Lambda REQUEST authorizer that checks API tokens
- Infrastructure-as-Code with Terraform using a single HTTP API Gateway (v2)

## High-level Architecture
- FastAPI application in `lambda/`, adapted for Lambda with `mangum`.
- Two sub-apps mounted under one root app:
  - `/api` → for web app usage (JWT auth), with docs at `/api/docs` and schema at `/api/openapi.json` (public)
  - `/gpt` → for GPT integrations (GET-only + token auth), with docs at `/gpt/docs` and schema at `/gpt/openapi.json` (public)
- Custom Lambda REQUEST authorizer in `lambda_authorizer/` validates `x-api-key` token against a DynamoDB table.
- Data stored in DynamoDB:
  - Table: `recallist_items` (partition key: `user_id`, sort key: `item` [normalized lowercase])
  - Table: `recallist_api_keys` (currently only for key-per-user, in future might be extended to identify lists)
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

Docs and schemas (public):
- `/api/docs`, `/api/openapi.json`
- `/gpt/docs`, `/gpt/openapi.json`

## Local Development
Although designed for Lambda, you can run FastAPI locally for quick testing:
- Install requirements from `lambda/requirements.txt`.
- Set AWS credentials pointing to a test account or local DynamoDB (adjust resource if needed).
- Run the app (example):
  ```bash
  uvicorn lambda.main:app --reload
  ```
  Note: In Lambda, the handler is created via `Mangum(app)`.