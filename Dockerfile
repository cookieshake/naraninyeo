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
RUN uv sync

# Install dependencies using uv
RUN uv pip install --no-cache -e .

# Copy project files
COPY naraninyeo/ naraninyeo/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "naraninyeo.main:app", "--host", "0.0.0.0", "--port", "8000"] 