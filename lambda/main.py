from fastapi import FastAPI, Request, HTTPException, Depends, Response, Body
from fastapi.responses import JSONResponse
from mangum import Mangum
from models import *
import db_service
import time
from utils import logging
from botocore.exceptions import ClientError
from typing import Dict, Any, List

# FASTAPI app and AWS Lambda handler
app = FastAPI()
handler = Mangum(app)

# Dependency to extract user info from the request
# Unified: prefer user_id provided by the custom authorizer, otherwise fall back to Cognito claims

def get_current_user(request: Request):
    authz = request.scope.get("aws.event", {}).get("requestContext", {}).get("authorizer", {})

    # Prefer unified user_id set by our REQUEST authorizer (works for Cognito OR API key)
    user_id = authz.get("user_id")

    # Fallback to Cognito claims if present (in case we call without custom authorizer somewhere)
    claims = authz.get("claims", {}) if isinstance(authz, dict) else {}
    if not user_id and claims:
        user_id = claims.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {
        "user_id": user_id
    }

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Generate a request ID for tracking
    logging.set_request_id()

    # Log the incoming request
    start_time = time.time()
    logging.info(f"Incoming request: {request.method} {request.url}")

    try:
        # Process the request
        response = await call_next(request)

        # Log the completed request
        process_time = time.time() - start_time
        logging.info(f"Completed request: {request.method} {request.url} with {response.status_code} in {process_time:.2f} seconds")

        return response
    finally:
        # Clear the request ID after the request is complete
        logging.clear_request_id()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the exception with full details
    logging.exception(f"Unhandled exception at {request.method} {request.url.path} - {str(exc)}")

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

def _to_item_model(db_obj: dict) -> Item:
    # Prefer original casing if stored, otherwise fallback to key
    item_text = db_obj.get("display_item") or db_obj.get("item")
    return Item(
        item=item_text,
        status=db_obj.get("status"),
        createdDate=db_obj.get("createdDate"),
        resolutionDate=db_obj.get("resolutionDate")
    )


@app.get(
    "/item/random",
    response_model=Item,
    summary="Get a random unresolved item",
    description="Returns one random item for the current user whose status is not RESOLVED.",
    operation_id="getRandomItem",
    responses={
        200: {"description": "A random unresolved item is returned."},
        404: {"description": "No unresolved items found for this user."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def get_random_item(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    logging.debug(f"Fetching random unresolved item for user {user_id}")
    db_obj = db_service.get_random_unresolved(user_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="No unresolved items found")
    return _to_item_model(db_obj)


@app.get(
    "/items",
    response_model=ItemList,
    summary="List all items",
    description="Returns all items for the current user, including both NEW and RESOLVED entries.",
    operation_id="listItems",
    responses={
        200: {"description": "List of items for the current user."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def get_items(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    logging.debug(f"Listing items for user {user_id}")
    items = db_service.list_items(user_id)
    return ItemList(items=[_to_item_model(x) for x in items])


@app.get(
    "/item/{item}",
    response_model=Item,
    summary="Get a specific item",
    description="Fetch a specific item for the current user with details. Lookup is case-insensitive.",
    operation_id="getItem",
    responses={
        200: {"description": "The requested item."},
        404: {"description": "Item not found."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def get_item(item: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    logging.debug(f"Getting item '{item}' for user {user_id}")
    db_obj = db_service.get_item(user_id, item)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Item not found")
    return _to_item_model(db_obj)


@app.delete(
    "/item/{item}",
    summary="Delete an item",
    description="Deletes a specific item for the current user. Operation is idempotent: returns 404 if it does not exist.",
    operation_id="deleteItem",
    responses={
        204: {"description": "Item deleted."},
        404: {"description": "Item not found."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def delete_word(item: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    logging.info(f"Deleting item '{item}' for user {user_id}")
    deleted = db_service.delete_item(user_id, item)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    return Response(status_code=204)


@app.patch(
    "/item/{item}",
    response_model=Item,
    summary="Resolve an item",
    description="Marks the specified item as RESOLVED and sets its resolution date to now.",
    operation_id="resolveItem",
    responses={
        200: {"description": "Item resolved."},
        404: {"description": "Item not found."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def resolve_item(item: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    logging.info(f"Resolving item '{item}' for user {user_id}")
    updated = db_service.mark_resolved(user_id, item)
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return _to_item_model(updated)


@app.post(
    "/item",
    response_model=Item,
    status_code=201,
    summary="Add an item to the list",
    description="Adds a new item to the list for the current user. The `item` text is stored case-insensitively for lookups while preserving original casing for display.",
    operation_id="addItem",
    responses={
        201: {"description": "Item created."},
        400: {"description": "Bad request (empty item text)."},
        409: {"description": "Item already exists."},
        401: {"description": "Unauthorized"}
    },
    tags=["items"]
)
async def save_item(
    item: Item = Body(
        ..., 
        example={"item": "Read Atomic Habits"}
    ), 
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    if not item.item or not item.item.strip():
        raise HTTPException(status_code=400, detail="Item text is required")
    logging.info(f"Creating item '{item.item}' for user {user_id}")
    try:
        created = db_service.put_item_if_absent(user_id, item.item)
        return _to_item_model(created)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            raise HTTPException(status_code=409, detail="Item already exists")
        # Re-raise as HTTP 500 with message
        raise HTTPException(status_code=500, detail=str(e))
