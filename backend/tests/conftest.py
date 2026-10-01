"""backend/tests/conftest.py"""

from pathlib import Path

import pandas as pd
import pytest

from app.database import SessionLocal

PROCESSED_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "cleaned_inventory.csv"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def reference_df() -> pd.DataFrame:
    """
    Independently loaded pandas dataframe (same source as the DB load) used
    to cross-check service-layer results against a computation path that
    doesn't share any code with the app itself.
    """
    return pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])
