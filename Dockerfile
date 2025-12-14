# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables to prevent interactive prompts during installation
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies including nginx with lua module
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    nginx-extras \
    lua-cjson \
    curl \
    procps \
    openssl \
    git \
    build-essential \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the application code
COPY . /app/

# Copy nginx configurations (both HTTP-only and HTTP+HTTPS versions)
COPY docker/nginx_rev_proxy_http_only.conf /app/docker/nginx_rev_proxy_http_only.conf
COPY docker/nginx_rev_proxy_http_and_https.conf /app/docker/nginx_rev_proxy_http_and_https.conf

# Make the entrypoint script executable
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# Expose ports for Nginx (HTTP/HTTPS) and the Registry (direct access, though usually proxied)
EXPOSE 80 443 7860

# Define environment variables for registry/server configuration (can be overridden at runtime)
# Provide sensible defaults or leave empty if they should be explicitly set
ARG BUILD_VERSION="1.0.0"
ARG SECRET_KEY=""
ARG ADMIN_USER="admin"
ARG ADMIN_PASSWORD=""
ARG POLYGON_API_KEY=""

ENV BUILD_VERSION=$BUILD_VERSION
ENV SECRET_KEY=$SECRET_KEY
ENV ADMIN_USER=$ADMIN_USER
ENV ADMIN_PASSWORD=$ADMIN_PASSWORD
ENV POLYGON_API_KEY=$POLYGON_API_KEY

# Add health check using the new HTTP endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Run the entrypoint script when the container launches
ENTRYPOINT ["/app/docker/entrypoint.sh"]