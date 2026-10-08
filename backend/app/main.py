"""
backend/app/main.py

FastAPI application entrypoint.

InventoryAI provides:

- authentication
- inventory management
- sales recording and analysis
- demand forecasting
- stockout risk analysis
- reorder recommendations
- NLP chatbot
- alerts
- dashboard analytics
- system settings
- model evaluation / health
- watchlist
- purchase orders
"""

from __future__ import annotations

import os

# Prevent macOS OpenMP duplicate runtime conflicts and thread deadlocks
# between scikit-learn and XGBoost.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    auth,
    briefing,
    chat,
    dashboard,
    forecast,
    health,
    inventory,
    live,
    model_health,
    products,
    purchase_orders,
    reorder,
    sales,
    settings as settings_router,
    stockout,
    watchlist,
    ws,
)
from app.security import (
    require_request_identity,
    unauthorized,
)
from app.services.errors import (
    InvalidRequestError,
    NotFoundError,
)

settings = get_settings()

logging.basicConfig(
    level=getattr(
        logging,
        settings.log_level,
        logging.INFO,
    )
)

log = logging.getLogger("app")


# -----------------------------------------------------------------------------
# FastAPI application
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Inventory Intelligence System API",
    description=(
        "Retail inventory analytics, demand forecasting, stockout risk, "
        "reorder recommendations, model evaluation, and NLP chatbot."
    ),
    version="0.1.0",
)


# -----------------------------------------------------------------------------
# CORS configuration
# -----------------------------------------------------------------------------

allowed_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

if not allowed_origins or "*" in allowed_origins:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must list specific trusted website origins; "
        "'*' is not allowed."
    )

development_origin_regex = (
    r"https?://(?:localhost|127\.0\.0\.1):\d+$"
    if settings.environment.lower() == "development"
    else None
)


# -----------------------------------------------------------------------------
# Authentication middleware
# -----------------------------------------------------------------------------

@app.middleware("http")
async def protect_api(
    request: Request,
    call_next,
):
    """
    Protect API endpoints with authentication.

    Public endpoints:
      /api/health
      /api/auth/login

    OPTIONS requests are allowed so that CORS preflight requests work.
    """

    public_paths = {
        "/api/health",
        "/api/auth/login",
    }

    is_api_request = request.url.path.startswith("/api/")
    is_public = request.url.path in public_paths
    is_preflight = request.method == "OPTIONS"

    if (
        is_api_request
        and not is_public
        and not is_preflight
    ):
        if require_request_identity(request) is None:
            exc = unauthorized()

            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": exc.detail,
                },
                headers=exc.headers,
            )

    return await call_next(request)


# -----------------------------------------------------------------------------
# CORS middleware
# -----------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=development_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type",
    ],
)


# -----------------------------------------------------------------------------
# Exception handlers
# -----------------------------------------------------------------------------

@app.exception_handler(NotFoundError)
def not_found_handler(
    request: Request,
    exc: NotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(InvalidRequestError)
def invalid_request_handler(
    request: Request,
    exc: InvalidRequestError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(Exception)
def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    log.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred.",
        },
    )


# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------

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

# Keep the Live backend router because Alerts still use:
#   /api/live/alerts
#   /api/live/digest
#
# We are removing the Live PAGE/UI, not the alert API.
app.include_router(live.router)

app.include_router(watchlist.router)
app.include_router(dashboard.router)

# Settings remain available as backend operations controls.
app.include_router(settings_router.router)

# Model Health remains available as backend ML evaluation.
# It is intentionally NOT added to the frontend navbar.
app.include_router(model_health.router)

# Purchase orders are used by the Reorder page.
app.include_router(purchase_orders.router)

# Morning briefing powers the dashboard banner; keep it registered even
# though it has no navbar entry of its own.
app.include_router(briefing.router)


# -----------------------------------------------------------------------------
# Root endpoint
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Inventory Intelligence System API",
        "docs": "/docs",
        "health": "/api/health",
        "settings": "/api/settings",
        "model_health": "/api/model-health",
    }