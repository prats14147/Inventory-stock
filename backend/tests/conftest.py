"""backend/tests/conftest.py"""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base  # noqa: F401  (ensures all models are registered)

PROCESSED_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "cleaned_inventory.csv"

_settings = get_settings()
_test_engine = create_engine(_settings.database_url, pool_pre_ping=True)
_TestSessionFactory = sessionmaker(bind=_test_engine, join_transaction_mode="create_savepoint")


@pytest.fixture()
def db():
    """A Postgres session wrapped in a transaction that is always rolled back.

    Every write a test (or the service code it calls) makes -- including
    ``db.commit()`` inside services -- is confined to a SAVEPOINT nested in
    this outer transaction, so ``connection.rollback()`` below discards ALL
    of it. Tests can therefore never pollute each other or the dev database,
    and no per-test cleanup code is needed. This replaces the old pattern of
    a bare ``SessionLocal()`` plus manual DELETE cleanups, which leaked writes
    (e.g. a recorded sale permanently lowered inventory and re-tagged a
    sample row, silently shifting reference values for later tests).
    """
    from app.database import get_db
    from app.main import app

    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionFactory(bind=connection)

    def _override_get_db():
        try:
            yield session
        finally:
            pass  # lifecycle owned by this fixture, not the request

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        transaction.rollback()
        connection.close()
        # Drop process-level caches that may hold frames read during the test.
        from app.repositories import sales_repository
        from app.services import stockout_service

        sales_repository.clear_history_cache()
        stockout_service.clear_risk_cache()


@pytest.fixture(scope="session")
def reference_df() -> pd.DataFrame:
    """
    Independently loaded pandas dataframe (same source as the DB load) used
    to cross-check service-layer results against a computation path that
    doesn't share any code with the app itself.
    """
    return pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    """Bypasses token verification in tests by setting identity to admin operator."""
    monkeypatch.setattr("app.main.require_request_identity", lambda req: "admin")
    monkeypatch.setattr("app.security.get_token_identity", lambda token: "admin")



