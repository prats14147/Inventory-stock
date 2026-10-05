"""
backend/app/main.py

FastAPI application entrypoint. Wires together every router built in
Phases 4-7. Error handling (spec section 46):
  - NotFoundError (unknown product, etc.)      -> 404
  - InvalidRequestError (bad date range, etc.)  -> 400
  - Pydantic validation errors                  -> 422 (handled by FastAPI automatically)
  - Anything else                               -> 500, logged, generic message
    (never leaks internal exception details to the client)
"""

from __future__ import annotations

import os

# Prevent macOS OpenMP duplicate runtime conflicts and thread deadlocks between sklearn and xgboost
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    auth,
    chat,
    dashboard,
    forecast,
    health,
    inventory,
    live,
    products,
    reorder,
    sales,
    stockout,
    watchlist,
    ws,
)
from app.services import simulator_service
from app.services.errors import InvalidRequestError, NotFoundError
from app.security import require_request_identity, unauthorized

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start/stop the demo data simulator with the app.

    The simulator is opt-in (SIMULATOR_ENABLED) and can also be started later
    from POST /api/simulator/start -- `docker compose up` therefore behaves
    exactly as before unless someone asks for live traffic.
    """
    if settings.simulator_enabled:
        started = simulator_service.get_simulator_service().start(asyncio.get_running_loop())
        log.info("Data simulator auto-start: %s", started)
    yield
    simulator_service.get_simulator_service().stop()


app = FastAPI(
    title="Inventory Intelligence System API",
    description="Retail inventory analytics, demand forecasting, stockout risk, reorder recommendations, and NLP chatbot.",
    version="0.1.0",
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
if not allowed_origins or "*" in allowed_origins:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must list specific trusted website origins; '*' is not allowed.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    # Health remains public for readiness probes, and login must be reachable
    # before a browser has a token. All other API data requires sign-in.
    public_paths = {"/api/health", "/api/auth/login"}
    if request.url.path.startswith("/api/") and request.url.path not in public_paths and request.method != "OPTIONS":
        if require_request_identity(request) is None:
            exc = unauthorized()
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
    return await call_next(request)


@app.exception_handler(NotFoundError)
def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidRequestError)
def invalid_request_handler(request: Request, exc: InvalidRequestError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(forecast.router)
app.include_router(stockout.router)
app.include_router(reorder.router)
app.include_router(chat.router)
app.include_router(ws.router)
app.include_router(live.router)
app.include_router(watchlist.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    return {
        "name": "Inventory Intelligence System API",
        "docs": "/docs",
        "health": "/api/health",
    }
