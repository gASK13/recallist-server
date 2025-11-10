from fastapi import Request, HTTPException
from botocore.exceptions import ClientError
from typing import Dict

from models import *
from db_service import *
from utils import *


def get_current_user(request: Request) -> Dict[str, str]:
    """Extract user identity from API Gateway v2 request context.
    Supports JWT authorizer (Cognito) and REQUEST authorizer (Lambda).
    """
    rc = request.scope.get("aws.event", {}).get("requestContext", {})
    authz = rc.get("authorizer", {}) or {}

    user_id = None

    # REQUEST authorizer can set context directly under authorizer
    if isinstance(authz, dict):
        user_id = authz.get("user_id") or user_id
        if not user_id and isinstance(authz.get("lambda"), dict):
            user_id = authz.get("lambda", {}).get("user_id")

    # JWT authorizer (Cognito) nests claims under authorizer.jwt.claims
    if not user_id and isinstance(authz, dict):
        jwt_section = authz.get("jwt")
        if isinstance(jwt_section, dict):
            claims = jwt_section.get("claims") or {}
            if isinstance(claims, dict):
                user_id = claims.get("sub")

    # Legacy fallback
    if not user_id and isinstance(authz, dict):
        claims = authz.get("claims") or {}
        if isinstance(claims, dict):
            user_id = claims.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"user_id": user_id}


# ---------- Shared helpers ----------

def _to_item_model(db_obj: dict) -> Item:
    item_text = db_obj.get("display_item") or db_obj.get("item")
    return Item(
        item=item_text,
        status=db_obj.get("status"),
        createdDate=db_obj.get("createdDate"),
        resolutionDate=db_obj.get("resolutionDate")
    )


# Service layer to avoid duplication between /api and /gpt
async def svc_get_random_item(user_id: str) -> Item:
    debug(f"Fetching random unresolved item for user {user_id}")
    db_obj = get_random_unresolved(user_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="No unresolved items found")
    return _to_item_model(db_obj)


async def svc_list_items(user_id: str) -> ItemList:
    debug(f"Listing items for user {user_id}")
    items = list_items(user_id)
    return ItemList(items=[_to_item_model(x) for x in items])


async def svc_get_item(user_id: str, item: str) -> Item:
    debug(f"Getting item '{item}' for user {user_id}")
    db_obj = get_item(user_id, item)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Item not found")
    return _to_item_model(db_obj)


async def svc_delete_item(user_id: str, item: str) -> None:
    info(f"Deleting item '{item}' for user {user_id}")
    deleted = delete_item(user_id, item)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")


async def svc_resolve_item(user_id: str, item: str) -> Item:
    info(f"Resolving item '{item}' for user {user_id}")
    updated = mark_resolved(user_id, item)
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return _to_item_model(updated)


async def svc_create_item(user_id: str, item_text: str) -> Item:
    if not item_text or not item_text.strip():
        raise HTTPException(status_code=400, detail="Item text is required")
    info(f"Creating item '{item_text}' for user {user_id}")
    try:
        created = put_item_if_absent(user_id, item_text)
        return _to_item_model(created)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            raise HTTPException(status_code=409, detail="Item already exists")
        raise HTTPException(status_code=500, detail=str(e))
