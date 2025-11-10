from fastapi import FastAPI, Depends, Response, Body

from recallist import *

api_app = FastAPI(name="Recallist Main API", version="1.0.0")

@api_app.get(
    "/item/random",
    response_model=Item,
    summary="Get a random unresolved item",
    description="Returns one random item for the current user whose status is not RESOLVED.",
    operation_id="getRandomItem",
    tags=["items"],
)
async def api_get_random_item(current_user: dict = Depends(get_current_user)):
    return await svc_get_random_item(current_user["user_id"])


@api_app.get(
    "/items",
    response_model=ItemList,
    summary="List all items",
    description="Returns all items for the current user, including both NEW and RESOLVED entries.",
    operation_id="listItems",
    tags=["items"],
)
async def api_get_items(current_user: dict = Depends(get_current_user)):
    return await svc_list_items(current_user["user_id"])


@api_app.get(
    "/item/{item}",
    response_model=Item,
    summary="Get a specific item",
    description="Fetch a specific item for the current user with details. Lookup is case-insensitive.",
    operation_id="getItem",
    tags=["items"],
)
async def api_get_item(item: str, current_user: dict = Depends(get_current_user)):
    return await svc_get_item(current_user["user_id"], item)


@api_app.delete(
    "/item/{item}",
    summary="Delete an item",
    description="Deletes a specific item for the current user. Operation is idempotent: returns 404 if it does not exist.",
    operation_id="deleteItem",
    status_code=204,
    tags=["items"],
)
async def api_delete_item(item: str, current_user: dict = Depends(get_current_user)):
    await svc_delete_item(current_user["user_id"], item)
    return Response(status_code=204)


@api_app.patch(
    "/item/{item}",
    response_model=Item,
    summary="Resolve an item",
    description="Marks the specified item as RESOLVED and sets its resolution date to now.",
    operation_id="resolveItem",
    tags=["items"],
)
async def api_resolve_item(item: str, current_user: dict = Depends(get_current_user)):
    return await svc_resolve_item(current_user["user_id"], item)


@api_app.post(
    "/item",
    response_model=Item,
    status_code=201,
    summary="Add an item to the list",
    description="Adds a new item to the list for the current user. The `item` text is stored case-insensitively while preserving original casing for display.",
    operation_id="addItem",
    tags=["items"],
)
async def api_save_item(
    item: Item = Body(..., example={"item": "Read Atomic Habits"}),
    current_user: dict = Depends(get_current_user),
):
    return await svc_create_item(current_user["user_id"], item.item)
