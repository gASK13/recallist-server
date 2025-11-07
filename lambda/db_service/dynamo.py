import boto3
import os
import random
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
from typing import Optional, List, Dict, Any

# DynamoDB setup
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
item_table_name = os.getenv("ITEM_TABLE", "recallist_items")
item_table = dynamodb.Table(item_table_name)
api_keys_table_name = os.getenv("API_KEYS_TABLE", "recallist_api_keys")
api_keys_table = dynamodb.Table(api_keys_table_name)

# Utilities

def _normalize_item_key(item: str) -> str:
    """Normalize item key to enforce case-insensitive behavior."""
    return (item or "").strip().lower()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Data access functions for items (per user)

def get_item(user_id: str, item: str) -> Optional[Dict[str, Any]]:
    """Get a single item by user and item key (case-insensitive)."""
    norm = _normalize_item_key(item)
    resp = item_table.get_item(Key={"user_id": user_id, "item": norm})
    return resp.get("Item")


def list_items(user_id: str) -> List[Dict[str, Any]]:
    """List all items for a user."""
    items: List[Dict[str, Any]] = []
    resp = item_table.query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    items.extend(resp.get("Items", []))
    # paginate if needed
    while 'LastEvaluatedKey' in resp:
        resp = item_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ExclusiveStartKey=resp['LastEvaluatedKey']
        )
        items.extend(resp.get("Items", []))
    return items


def list_unresolved_items(user_id: str) -> List[Dict[str, Any]]:
    """List all unresolved items for a user."""
    items: List[Dict[str, Any]] = []
    resp = item_table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression=Attr("status").ne("RESOLVED")
    )
    items.extend(resp.get("Items", []))
    while 'LastEvaluatedKey' in resp:
        resp = item_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=Attr("status").ne("RESOLVED"),
            ExclusiveStartKey=resp['LastEvaluatedKey']
        )
        items.extend(resp.get("Items", []))
    return items


def get_random_unresolved(user_id: str) -> Optional[Dict[str, Any]]:
    items = list_unresolved_items(user_id)
    if not items:
        return None
    return random.choice(items)


def put_item_if_absent(user_id: str, item: str, created_iso: Optional[str] = None) -> Dict[str, Any]:
    """Create a new item with status NEW. Fails if already exists."""
    norm = _normalize_item_key(item)
    if created_iso is None:
        created_iso = now_iso()
    new_item = {
        "user_id": user_id,
        "item": norm,
        "display_item": item,  # preserve original casing for display
        "status": "NEW",
        "createdDate": created_iso,
        # resolutionDate omitted when NEW
    }
    item_table.put_item(
        Item=new_item,
        ConditionExpression=Attr("item").not_exists()
    )
    return new_item


def delete_item(user_id: str, item: str) -> bool:
    """Delete an item. Returns True if deleted, False if not found."""
    norm = _normalize_item_key(item)
    try:
        item_table.delete_item(
            Key={"user_id": user_id, "item": norm},
            ConditionExpression=Attr("item").exists()
        )
        return True
    except Exception:
        return False


def mark_resolved(user_id: str, item: str, resolution_iso: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Mark an item as RESOLVED and set resolutionDate. Returns updated item or None if not exists."""
    norm = _normalize_item_key(item)
    if resolution_iso is None:
        resolution_iso = now_iso()
    try:
        resp = item_table.update_item(
            Key={"user_id": user_id, "item": norm},
            UpdateExpression="SET #s = :resolved, resolutionDate = :rd",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":resolved": "RESOLVED", ":rd": resolution_iso},
            ConditionExpression=Attr("item").exists(),
            ReturnValues="ALL_NEW"
        )
        return resp.get("Attributes")
    except Exception:
        return None