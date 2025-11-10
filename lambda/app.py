from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from mangum import Mangum
import time

# Import sub-apps (modules live at the zip root)
from api_app import api_app
from gpt_app import gpt_app
from utils import *

# Root FASTAPI app (no docs at root) and AWS Lambda handler
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

# Mount sub-apps under the root app
app.mount("/api", api_app)
app.mount("/gpt", gpt_app)

@app.middleware("http")
async def log_requests_api(request: Request, call_next):
    if request.url.path.startswith("/gpt"):
        print("🔍 Headers received:", dict(request.headers))
    set_request_id()
    start_time = time.time()
    info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        info(
            f"Completed request: {request.method} {request.url} with {response.status_code} in {process_time:.2f} seconds"
        )
        return response
    finally:
        clear_request_id()


@app.exception_handler(Exception)
async def api_global_exception_handler(request: Request, exc: Exception):
    exception(f"Unhandled exception at {request.method} {request.url.path} - {str(exc)}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "error": str(exc)})


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# AWS Lambda handler
handler = Mangum(app)
