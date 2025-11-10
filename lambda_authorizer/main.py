import os
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key

API_KEYS_TABLE = os.getenv("API_KEYS_TABLE", "recallist_api_keys")
dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
api_keys_table = dynamodb.Table(API_KEYS_TABLE)


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
            "auth_type": "x-api-key"
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


def _lookup_user_id_by_api_key(api_key: str) -> str | None:
    # Table schema: PK=api_key, SK=user_id
    try:
        resp = api_keys_table.query(KeyConditionExpression=Key("api_key").eq(api_key))
        items = resp.get("Items") or []
        if not items:
            return None
        # Choose the first matching mapping
        return items[0].get("user_id")
    except Exception:
        return None


def handler(event, context):
    print("Authorizer event received:", event)
    # REQUEST authorizer: validate x-api-key by looking it up in DynamoDB
    try:
        print("Extracting headers for API key lookup")
        headers = event.get("headers") or {}
        headers = {(k.lower() if isinstance(k, str) else k): v for k, v in headers.items()}

        api_key = headers.get("x-api-key")
        if not api_key:
            return _deny()

        print("Looking up user ID for provided API key")
        user_id = _lookup_user_id_by_api_key(api_key.strip())
        if not user_id:
            return _deny()

        print("Valid API key; allowing access for user:", user_id)

        return _allow(principal_id="apiKeyUser", user_id=user_id)
    except Exception:
        print(f"Error in authorizer: {str(Exception)}")
        return _deny()
