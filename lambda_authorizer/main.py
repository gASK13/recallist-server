import json
import os
import base64
import time
from typing import Any, Dict

import boto3

# NOTE: For production, you should verify the Cognito JWT signature using JWKS.
# This minimal implementation only performs lightweight checks on the token structure and claims
# to demonstrate the either-OR behavior with API key. Replace the JWT part with proper verification.


def _parse_bearer_token(auth_header: str) -> str | None:
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _decode_jwt_no_verify(token: str) -> Dict[str, Any] | None:
    # Very light parsing without signature verification. DO NOT use in production.
    try:
        # JWT is header.payload.signature (base64url)
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # Fix padding
        padding = '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        return payload
    except Exception:
        return None


def _allow(principal_id: str, user_id: str) -> Dict[str, Any]:
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": "*"
                }
            ]
        },
        "context": {
            # Expose a unified field for downstream Lambda (FastAPI) to read
            # It will be available at event.requestContext.authorizer.user_id
            "user_id": user_id,
            # Optional: include auth_type for debugging/metrics
            "auth_type": "either-or"
        }
    }


def _deny() -> Dict[str, Any]:
    return {
        "principalId": "anonymous",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": "*"
                }
            ]
        }
    }


def handler(event, context):
    # REQUEST authorizer: we have access to headers/query/path
    headers = event.get("headers") or {}
    headers = { (k.lower() if isinstance(k, str) else k): v for k, v in headers.items() }

    auth_header = headers.get("authorization")

    # 1) Try Cognito JWT path (weak parsing; replace with proper verification in prod)
    token = _parse_bearer_token(auth_header) if auth_header else None
    if token:
        payload = _decode_jwt_no_verify(token)
        if payload and payload.get("sub") and payload.get("iss"):
            # Optional basic sanity checks
            user_pool_id = os.environ.get("USER_POOL_ID")
            expected_iss_prefix = f"https://cognito-idp.us-east-1.amazonaws.com/{user_pool_id}" if user_pool_id else None
            if not expected_iss_prefix or str(payload.get("iss", "")).startswith(expected_iss_prefix):
                return _allow(principal_id="cognitoUser", user_id=payload["sub"])  # prefer Cognito sub

    # 2) Try DynamoDB API key path - treat token as API KEY
    if auth_header:
        api_keys_table = os.environ.get("API_KEYS_TABLE", "recallist_api_keys")
        ddb = boto3.resource("dynamodb")
        table = ddb.Table(api_keys_table)
        # The table is defined with hash_key=api_key and range_key=user_id
        # We don't know the user_id yet, so scan on api_key (small test usage). For production,
        # consider a GSI or store api_key as hash only. Here we perform a Query via a secondary index
        # if available; otherwise do a scan as a fallback.
        # Try a direct query on a GSI named api_key-index if it exists; otherwise scan.
        user_id = None
        try:
            # Attempt a Query on ApiKeyGsi (if the user adds it later). If it fails, we scan.
            resp = table.scan(
                FilterExpression="#k = :v",
                ExpressionAttributeNames={"#k": "api_key"},
                ExpressionAttributeValues={":v": auth_header},
                ProjectionExpression="user_id"
            )
            items = resp.get("Items", [])
            if items:
                user_id = items[0].get("user_id")
        except Exception:
            user_id = None
        if user_id:
            return _allow(principal_id="apiKeyUser", user_id=user_id)

    # Otherwise deny
    return _deny()
