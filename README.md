# recallist-server

Recallist is a lightweight Model Context Protocol (MCP) server that gives GPT-based agents a simple, persistent, per-user item list. Agents can add notes, mark them resolved, fetch a random unresolved item, and list everything — useful for micro-learning, spaced repetition, reminders, and lightweight personal memory.

## Key Features
- Simple REST API built with FastAPI (served via AWS Lambda + API Gateway)
- Per-user storage in DynamoDB with case-insensitive keys, preserving original casing for display
- Random unresolved item retrieval for spaced repetition workflows
- Either/Or auth: Cognito JWT (Authorization: Bearer …) or API Key (x-api-key)
- Infrastructure-as-Code with Terraform

## High-level Architecture
- FastAPI application in `lambda/`, adapted for Lambda with `mangum`.
- Custom API Gateway REQUEST authorizer in `lambda_authorizer/` that accepts:
  - Authorization: Bearer <Cognito JWT> (minimal parsing in sample; replace with JWKS verification for production)
  - x-api-key header mapped to a `user_id` via DynamoDB `recallist_api_keys` table
- Data stored in DynamoDB:
  - Table: `recallist_items` (partition key: `user_id`, sort key: `item` [normalized lowercase])
  - Table: `recallist_api_keys` (partition key: `api_key`, sort key: `user_id`)
- Terraform definitions in `infra/main.tf` provision IAM, DynamoDB, API Gateway, and Lambda wiring.

## Data Model (DynamoDB)
Items are stored per user with a normalized item key for case-insensitive behavior.
- user_id: string (PK)
- item: string (SK, normalized lowercase of the item text)
- display_item: string (original user-provided text, preserved for display)
- status: "NEW" | "RESOLVED"
- createdDate: ISO8601 UTC string
- resolutionDate: ISO8601 UTC string (when resolved)

## API Overview
All endpoints require authorization via the custom authorizer (either Cognito JWT or x-api-key).

- GET `/item/random` → 200 with a random unresolved item; 404 if none
- GET `/items` → 200 with all items (resolved and unresolved)
- GET `/item/{item}` → 200 with a single item; 404 if not found (case-insensitive)
- POST `/item` → 201 creates a new item `{ item: string }`; 409 if duplicate; 400 if empty
- PATCH `/item/{item}` → 200 marks as RESOLVED and sets `resolutionDate`; 404 if not found
- DELETE `/item/{item}` → 204 on success; 404 if not found

See `lambda/main.py` and `lambda/models/models.py` for request/response models. An OpenAPI generator script is available in `lambda/openapi.py` and produces two specs:
- `lambda/openapi.yaml` (OpenAPI 3.0.0) — API Gateway import, includes AWS vendor extensions and custom authorizer wiring.
- `lambda/openapi.gpt.yaml` (OpenAPI 3.1.0) — GPT/MCP friendly, no auth/security sections or AWS vendor extensions.

## Authorization
Implemented as an API Gateway REQUEST authorizer (see `lambda_authorizer/main.py`). The authorizer sets `requestContext.authorizer.user_id` which the FastAPI app uses to scope all operations.
- Cognito path: `Authorization: Bearer <JWT>` → extracts `sub` as `user_id` (sample implementation does not verify signature and does not currently work, since the pool has no clients)
- API key path: `x-api-key: <key>` → looks up `user_id` in `recallist_api_keys` table (manual API key management for now)

## Environment Variables
- `ITEM_TABLE` (default: `recallist_items`)
- `API_KEYS_TABLE` (default: `recallist_api_keys`)
- `LOG_LEVEL` (default: `INFO`)
- `ENVIRONMENT` (default: `development`; affects log formatting)
- `USER_POOL_ID` (used by authorizer for basic issuer check when using Cognito)

## Local Development
Although designed for Lambda, you can run FastAPI locally for quick testing:
- Install requirements from `lambda/requirements.txt`.
- Set AWS credentials pointing to a test account or local DynamoDB (adjust resource if needed).
- Run the app (example):
  ```bash
  uvicorn lambda.main:app --reload
  ```
  Note: In Lambda, the handler is created via `Mangum(app)`.

To generate OpenAPI (with API Gateway extensions placeholders):
```bash
python lambda/openapi.py
```

## Deployment (Terraform)
The Terraform stack in `infra/main.tf` provisions the AWS resources. Typical flow:
- Ensure the Lambda deployment ZIP contains the `lambda/` sources and dependencies.
- `terraform init`
- `terraform plan`
- `terraform apply`
