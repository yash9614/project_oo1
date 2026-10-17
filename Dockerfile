FROM python:3.12-slim

WORKDIR /app

# Install system deps needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Make sure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Run the FastAPI app
CMD ["uvicorn", "assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]