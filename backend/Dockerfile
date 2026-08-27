FROM python:3.11-slim

# Install uv (fast pip replacement)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install deps first (better layer caching)
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy application source
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
