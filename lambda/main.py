from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from mangum import Mangum
from models import *
import db_service
import time
from utils import logging

# FASTAPI app and AWS Lambda handler
app = FastAPI()
handler = Mangum(app)

# Dependency to extract user info from the request
def get_current_user(request: Request):
    # TBA - add handling of API KEY presence instead of Cognito claim
    # TBA - in such case, get user from dynamo table if possible (we do not need email or username, just user_id)
    claims = request.scope.get("aws.event", {}).get("requestContext", {}).get("authorizer", {}).get("claims", {})
    if not claims:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "user_id": claims.get("sub"),
        "email": claims.get("email"),
        "username": claims.get("cognito:username"),
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

@app.get("/item/random", response_model=Item)
async def get_random_item(current_user: dict = Depends(get_current_user)):
    # TBA - get random UNRESOLVED item from dynamo table based on User
    return None

@app.get("/items", response_model=ItemList)
async def get_items(current_user: dict = Depends(get_current_user)):
    # TBA - get all items (both resolved and unresolved) for User
    return None

@app.get("/item/{item}", response_model=Item)
async def get_item(item: str, current_user: dict = Depends(get_current_user)):
    # TBA - get item from dynamo table based on User
    return None

@app.delete("/item/{item}")
async def delete_word(item: str, current_user: dict = Depends(get_current_user)):
    # TBA - delete item from dynamo table based on User
    return None

@app.patch("/item/{item}")
async def resolve_item(item: str, current_user: dict = Depends(get_current_user)):
    # TBA - mark item as RESOLVED in dynamo table based on User and set date to NOW
    return None

@app.post("/item", response_model=Item)
async def save_item(item: Item, current_user: dict = Depends(get_current_user)):
    # TBA - save item to dynamo table based on User, set createdDate to NOW
    # in case of existing item, do not modify and fail!
    return None
