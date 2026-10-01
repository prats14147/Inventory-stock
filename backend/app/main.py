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

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import chat, forecast, health, inventory, products, reorder, sales, stockout
from app.services.errors import InvalidRequestError, NotFoundError

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
log = logging.getLogger("app")

app = FastAPI(
    title="Inventory Intelligence System API",
    description="Retail inventory analytics, demand forecasting, stockout risk, reorder recommendations, and NLP chatbot.",
    version="0.1.0",
)

# Dev-friendly CORS. allow_credentials is deliberately False: this app
# uses no cookie-based auth, and allow_credentials=True combined with a
# wildcard origin is a contradictory CORS configuration per the spec
# (browsers forbid it) -- it was caught during Phase 10 integration
# testing producing inconsistent headers between simple and preflight
# requests. Tighten allow_origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(forecast.router)
app.include_router(stockout.router)
app.include_router(reorder.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {
        "name": "Inventory Intelligence System API",
        "docs": "/docs",
        "health": "/api/health",
    }
