# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY bot/ bot/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Pre-download the embedding model so runtime has no network dependency
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy cached model from builder (stored in HuggingFace cache default path)
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

WORKDIR /app
COPY bot/ bot/
COPY alembic/ alembic/
COPY alembic.ini .

VOLUME ["/data"]

ENTRYPOINT ["sh", "-c", "alembic upgrade head && python -m bot.main"]
