# NOTE: This Dockerfile has NOT been build-tested (no Docker available in
# the environment this project was built in). Verify with
# `docker compose up --build` before relying on it.

FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 (build from source if the wheel isn't available
# for this platform) and xgboost's runtime needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend application code.
COPY backend/ ./backend/

# Trained model artifacts -- required for the forecast/stockout/reorder
# services to load without retraining (spec section 24).
COPY ml/artifacts/ ./ml/artifacts/
COPY ml/features/ ./ml/features/

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
