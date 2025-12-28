#!/usr/bin/env python3
"""
MCP Gateway Registry - Modern FastAPI Application

A clean, domain-driven FastAPI app for managing MCP (Model Context Protocol) servers.
This main.py file serves as the application coordinator, importing and registering 
domain routers while handling core app configuration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Any
from pathlib import Path

from fastapi import FastAPI, Cookie, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from registry.auth.middleware import UnifiedAuthMiddleware
# Import domain routers
from registry.auth.routes import router as auth_router
from registry.api.server_routes import router as servers_router
from registry.api.server_routes_v1 import router as servers_router_v1
from registry.api.internal_routes import router as internal_router
from registry.api.search_routes import router as search_router
from registry.api.wellknown_routes import router as wellknown_router
from registry.api.registry_routes import router as registry_router
from registry.api.agent_routes import router as agent_router
from registry.health.routes import router as health_router
from registry.proxy.routes import router as proxy_router, shutdown_proxy_client

from registry.auth.dependencies import CurrentUser

# Import services for initialization
from registry.services.server_service import server_service
from registry.services.agent_service import agent_service
from registry.search.service import vector_service
from registry.health.service import health_service
from registry.services.federation_service import get_federation_service

# Import core configuration
from registry.core.config import settings

# Import MongoDB connection management
from packages.db.mongodb import init_mongodb, close_mongodb


# Configure logging with file and console handlers
def setup_logging():
    """Configure logging to write to both file and console."""
    import sys
    
    # Ensure log directory exists
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Define log file path
    log_file = log_dir / "registry.log"

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
    )

    console_formatter = logging.Formatter(
        '%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler with UTF-8 encoding to handle emojis
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)

    # Console handler with UTF-8 encoding to handle emojis on Windows
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    # Force UTF-8 encoding for console output on Windows
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Silently ignore if reconfigure fails

    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file


# Setup logging
log_file_path = setup_logging()
logger = logging.getLogger(__name__)
logger.info(f"Logging configured. Writing to file: {log_file_path}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info("🚀 Starting MCP Gateway Registry...")

    try:
        # Initialize MongoDB connection first
        logger.info("🗄️  Initializing MongoDB connection...")
        await init_mongodb()
        logger.info("✅ MongoDB connection established")
        
        # Initialize services in order
        logger.info("📚 Loading server definitions and state...")
        server_service.load_servers_and_state()

        logger.info("🔍 Initializing vector search service...")
        await vector_service.initialize()

        # Only update index if service initialized successfully
        if hasattr(vector_service, '_initialized') and vector_service._initialized:
            logger.info("📊 Updating vector search index with all registered services...")
            all_servers = server_service.get_all_servers()
            for service_path, server_info in all_servers.items():
                is_enabled = server_service.is_service_enabled(service_path)
                try:
                    await vector_service.add_or_update_service(service_path, server_info, is_enabled)
                    logger.debug(f"Updated vector search index for service: {service_path}")
                except Exception as e:
                    logger.warning(f"Failed to update index for service {service_path}: {e}")

            logger.info(f"✅ Vector index updated with {len(all_servers)} services")

            logger.info("📋 Loading agent cards and state...")
            agent_service.load_agents_and_state()
            logger.info("📊 Updating vector index with all registered agents...")
            all_agents = agent_service.list_agents()
            for agent_card in all_agents:
                is_enabled = agent_service.is_agent_enabled(agent_card.path)
                try:
                    await vector_service.add_or_update_agent(agent_card.path, agent_card)
                    logger.debug(f"Updated vector index for agent: {agent_card.path}")
                except Exception as e:
                    logger.error(f"Failed to update vector index for agent {agent_card.path}: {e}", exc_info=True)

            logger.info(f"✅ Vector search index updated with {len(all_agents)} services")
        else:
            logger.warning("⚠️  Vector search service not initialized - index update skipped")
            logger.info("💡 App will continue without vector search features")

        logger.info("🏥 Initializing health monitoring service...")
        await health_service.initialize()

        logger.info("🔗 Initializing federation service...")
        federation_service = get_federation_service()
        if federation_service.config.is_any_federation_enabled():
            logger.info(f"Federation enabled for: {', '.join(federation_service.config.get_enabled_federations())}")

            # Sync on startup if configured
            sync_on_startup = (
                    (
                                federation_service.config.anthropic.enabled and federation_service.config.anthropic.sync_on_startup) or
                    (federation_service.config.asor.enabled and federation_service.config.asor.sync_on_startup)
            )

            if sync_on_startup:
                logger.info("🔄 Syncing servers from federated registries on startup...")
                try:
                    sync_results = federation_service.sync_all()
                    for source, servers in sync_results.items():
                        logger.info(f"✅ Synced {len(servers)} servers from {source}")
                except Exception as e:
                    logger.error(f"⚠️ Federation sync failed (continuing with startup): {e}", exc_info=True)
        else:
            logger.info("Federation is disabled")
        logger.info("✅ All services initialized successfully!")

    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}", exc_info=True)
        raise

    # Application is ready
    yield

    # Shutdown tasks
    logger.info("🔄 Shutting down MCP Gateway Registry...")
    try:
        # Shutdown services gracefully
        await health_service.shutdown()
        await shutdown_proxy_client()
        
        # Close MongoDB connection
        logger.info("🗄️  Closing MongoDB connection...")
        await close_mongodb()
        
        logger.info("✅ Shutdown completed successfully!")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="MCP Gateway Registry",
    description="A registry and management system for Model Context Protocol (MCP) servers",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for React development and Docker deployment
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost(:[0-9]+)?|.*\.compute.*\.amazonaws\.com(:[0-9]+)?)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(
    UnifiedAuthMiddleware
)

# Register API routers with /api prefix
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(servers_router, prefix="/api", tags=["Server Management"])
app.include_router(servers_router_v1, prefix="/api", tags=["Server Management V1"])
app.include_router(internal_router, prefix="/api", tags=["Server Management[internal]"])
app.include_router(agent_router, prefix="/api", tags=["Agent Management"])
app.include_router(search_router, prefix="/api/search", tags=["Semantic Search"])
app.include_router(health_router, prefix="/api/health", tags=["Health Monitoring"])

# Register Anthropic MCP Registry API (public API for MCP servers only)
app.include_router(registry_router, tags=["Anthropic Registry API"])

# Register well-known discovery router
app.include_router(wellknown_router, prefix="/.well-known", tags=["Discovery"])


# Add user info endpoint for React auth context
@app.get("/api/auth/me")
async def get_current_user(user_context: CurrentUser):
    """Get current user information for React auth context"""
    # Return user info with scopes for token generation
    return {
        "username": user_context["username"],
        "auth_method": user_context.get("auth_method", "basic"),
        "provider": user_context.get("provider"),
        "scopes": user_context.get("scopes", []),
        "groups": user_context.get("groups", []),
        "can_modify_servers": user_context.get("can_modify_servers", False),
        "is_admin": user_context.get("is_admin", False)
    }


# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "healthy", "service": "mcp-gateway-registry"}


app.include_router(proxy_router, prefix="/proxy", tags=["MCP Proxy"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "registry.main:app",
        host="0.0.0.0",
        port=7860,
        reload=True,
        log_level="info"
    )
