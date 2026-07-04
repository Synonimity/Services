FROM python:3.14-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Install build dependencies if needed (e.g., for argon2-cffi or asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.14-slim

WORKDIR /app

# Copy installed dependencies
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Set default env vars
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
