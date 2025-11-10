ARG TARGETPLATFORM=linux/arm64
FROM --platform=${TARGETPLATFORM} public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy dependency files (deploy scripts copy these to .tmp/ directory before build)
COPY .tmp/pyproject.toml .tmp/uv.lock ./

# Install Python dependencies using uv (as root, before switching users)
RUN uv sync --frozen --no-dev

# Copy agent code (current directory)
COPY . ./

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore

# Create data directory for SQLite database with proper ownership
# Also fix ownership of installed packages
RUN mkdir -p /app/data && \
    chown -R bedrock_agentcore:bedrock_agentcore /app

USER bedrock_agentcore

# Set environment variables
ENV PYTHONPATH=/app
ENV AWS_REGION=us-east-1
ENV AWS_DEFAULT_REGION=us-east-1

# Expose port for A2A communication (port 9000 for A2A protocol)
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/ping || exit 1

# Run the agent with uv (uses the virtual environment created by uv sync)
CMD ["uv", "run", "--no-sync", "agent.py"]
