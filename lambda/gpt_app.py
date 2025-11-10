from fastapi import FastAPI, Depends, Response, Query

from recallist import *

# GPT-focused FastAPI app exposing GET-only endpoints
# This app is mounted under /gpt by the root app

gpt_app = FastAPI(name="Recallist GPT API (GET-only)", version="1.0.0")


@gpt_app.get(
    "/items",
    response_model=ItemList,
    summary="List all items",
    description="Returns all items for the current user, including both NEW and RESOLVED entries.",
    operation_id="gptListItems",
    tags=["gpt"],
)
async def gpt_list_items(current_user: dict = Depends(get_current_user)):
    return await svc_list_items(current_user["user_id"])


@gpt_app.get(
    "/item/random",
    response_model=Item,
    summary="Get a random unresolved item",
    description="Returns one random item for the current user whose status is not RESOLVED.",
    operation_id="gptGetRandomItem",
    tags=["gpt"],
)
async def gpt_get_random_item(current_user: dict = Depends(get_current_user)):
    return await svc_get_random_item(current_user["user_id"])


@gpt_app.get(
    "/item/{item}",
    response_model=Item,
    summary="Get a specific item",
    description="Fetch a specific item for the current user with details. Lookup is case-insensitive.",
    operation_id="gptGetItem",
    tags=["gpt"],
)
async def gpt_get_item(item: str, current_user: dict = Depends(get_current_user)):
    return await svc_get_item(current_user["user_id"], item)


@gpt_app.get(
    "/item/{item}/delete",
    summary="Delete an item (GET)",
    description="Deletes a specific item for the current user. Returns 204 on success; 404 if not found.",
    operation_id="gptDeleteItem",
    status_code=204,
    tags=["gpt"],
)
async def gpt_delete_item(item: str, current_user: dict = Depends(get_current_user)):
    await svc_delete_item(current_user["user_id"], item)
    return Response(status_code=204)


@gpt_app.get(
    "/item/{item}/resolve",
    response_model=Item,
    summary="Resolve an item (GET)",
    description="Marks the specified item as RESOLVED and sets its resolution date to now.",
    operation_id="gptResolveItem",
    tags=["gpt"],
)
async def gpt_resolve_item(item: str, current_user: dict = Depends(get_current_user)):
    return await svc_resolve_item(current_user["user_id"], item)


@gpt_app.get(
    "/item/add",
    response_model=Item,
    status_code=201,
    summary="Add an item to the list (GET)",
    description="Adds a new item to the list for the current user via query param `item`.",
    operation_id="gptAddItem",
    tags=["gpt"],
)
async def gpt_add_item(item: str = Query(..., description="Item text to add"), current_user: dict = Depends(get_current_user)):
    return await svc_create_item(current_user["user_id"], item)

