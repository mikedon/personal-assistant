# Multi-stage Dockerfile for Personal Assistant
# Stage 1: Base dependencies
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Copy source code (needed for editable install)
COPY src ./src

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Stage 2: Development image
FROM base AS development

# Install development dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY --chown=appuser:appuser . .

# Create data directory for SQLite and OAuth tokens
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Default command for development (API server with reload)
CMD ["pa", "server", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 3: Production image
FROM base AS production

# Copy application code
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini .

# Create data directory for SQLite and OAuth tokens
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command for production (API server)
CMD ["pa", "server", "--host", "0.0.0.0", "--port", "8000"]
