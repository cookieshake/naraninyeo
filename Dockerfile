# Use Python 3.13 slim image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin/:$PATH"

# Copy pyproject.toml first to leverage Docker cache
COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --no-dev

# RUN uv run crawl4ai-setup && \
#     uv run crawl4ai-doctor

# Copy project files
COPY naraninyeo/ naraninyeo/
COPY main.py main.py

# Set OpenTelemetry environment variables
# Replace the placeholder values with your actual configuration.
ENV OTEL_RESOURCE_ATTRIBUTES="service.name=naraninyeo"
ENV OTEL_EXPORTER_OTLP_ENDPOINT="http://signoz.vd.ingtra.net:4318"
ENV OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"

# Run the application with OpenTelemetry instrumentation - using kafka consumer mode
CMD ["uv", "run", "python", "main.py", "kafka"]
