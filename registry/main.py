#!/usr/bin/env python3
"""
MCP Gateway Registry - Modern FastAPI Application

A clean, domain-driven FastAPI app for managing MCP (Model Context Protocol) servers.
This main.py file serves as the application coordinator, importing and registering 
domain routers while handling core app configuration.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from packages.database import init_mongodb, close_mongodb
from packages.database.redis_client import init_redis, close_redis
from registry.auth.middleware import UnifiedAuthMiddleware
from registry.core.config import settings
from pathlib import Path
from fastapi.staticfiles import StaticFiles
# Import domain routers
from registry.api.v1.meta_routes import router as meta_router
from registry.api.v1.token_routes import router as token_router
from registry.api.v1.server.server_routes import router as servers_router_v1
from registry.api.v1.search_routes import router as search_router
from registry.api.wellknown_routes import router as wellknown_router
from registry.api.agent_routes import router as agent_router
from registry.api.management_routes import router as management_router
from registry.health.routes import router as health_router
from registry.api.v1.mcp.oauth_router import router as oauth_router
from registry.api.redirect_routes import router as auth_provider_router
from registry.api.v1.mcp.connection_router import router as connection_router
from registry.api.v1.acl_routes import router as acl_router
from registry.version import __version__
from registry.api.proxy_routes import router as proxy_router, shutdown_proxy_client
from registry.auth.dependencies import CurrentUserWithACLMap
from packages.models._generated import IUser

# Import services for initialization
from registry.services.agent_service import agent_service
from registry.health.service import health_service
from registry.services.federation_service import get_federation_service
from registry.services.search.service import vector_service

from registry.utils.log import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info("🚀 Starting MCP Gateway Registry...")

    try:
        # Initialize MongoDB connection first
        logger.info("🗄️  Initializing MongoDB connection...")
        await init_mongodb()
        logger.info("✅ MongoDB connection established")
        
        # Initialize Redis connection
        logger.info("🔴 Initializing Redis connection...")
        await init_redis()
        logger.info("✅ Redis connection established")
        
        logger.info("🔍 Initializing vector search service...")
        await vector_service.initialize()

        # Only update index if service initialized successfully
        if hasattr(vector_service, '_initialized') and vector_service._initialized:
            logger.info("📊 Updating vector search index with all registered services...")
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
        
        # Close Redis connection
        logger.info("🔴 Closing Redis connection...")
        await close_redis()
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
    version=__version__,
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "OAuth2 and session-based authentication endpoints"
        },
        {
            "name": "Server Management",
            "description": "MCP server registration and management. Requires JWT Bearer token authentication."
        },
        {
            "name": "Agent Management",
            "description": "A2A agent registration and management. Requires JWT Bearer token authentication."
        },
        {
            "name": "Management API",
            "description": "IAM and user management operations. Requires JWT Bearer token with admin permissions."
        },
        {
            "name": "Semantic Search",
            "description": "Vector-based semantic search for agents. Requires JWT Bearer token authentication."
        },
        {
            "name": "Health Monitoring",
            "description": "Service health check endpoints"
        },
        {
            "name": "Anthropic Registry API",
            "description": "Anthropic-compatible registry API (v0.1) for MCP server discovery"
        }
    ]
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

if hasattr(settings, 'static_dir') and Path(settings.static_dir).exists():
    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    logger.info(f"Static files mounted from {settings.static_dir}")
else:
    logger.warning("Static files directory not found, skipping static files mount")

# Register API routers with /api prefix
app.include_router(meta_router, prefix="/api/auth", tags=["Authentication metadata"])
app.include_router(token_router, prefix="/api", tags=["Server Management"])
app.include_router(servers_router_v1, prefix=f"/api/{settings.API_VERSION}", tags=["Server Management V1"])
app.include_router(agent_router, prefix="/api", tags=["Agent Management"])
app.include_router(management_router, prefix="/api")
app.include_router(search_router, prefix=f"/api/{settings.API_VERSION}", tags=["Semantic Search"])
app.include_router(health_router, prefix="/api/health", tags=["Health Monitoring"])
app.include_router(oauth_router, prefix=f"/api/{settings.API_VERSION}", tags=["MCP  Oauth Management"])
app.include_router(connection_router, prefix=f"/api/{settings.API_VERSION}", tags=["MCP  Connection Management"])
app.include_router(acl_router, prefix=f"/api/{settings.API_VERSION}", tags=["ACL Management"])
app.include_router(auth_provider_router, tags=["Authentication"])

# Register Anthropic MCP Registry API (public API for MCP servers only)

# Register well-known discovery router
app.include_router(wellknown_router, prefix="/.well-known", tags=["Discovery"])


# Customize OpenAPI schema to add security schemes
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token obtained from Keycloak OAuth2 authentication. "
                           "Include in Authorization header as: `Authorization: Bearer <token>`"
        }
    }

    # Apply Bearer security to all endpoints except auth, health, and public discovery endpoints
    for path, path_item in openapi_schema["paths"].items():
        # Skip authentication, health check, and public discovery endpoints
        if path.startswith("/api/auth/") or path == "/health" or path.startswith("/.well-known/"):
            continue

        # Apply Bearer security to all methods in this path
        for method in path_item:
            if method in ["get", "post", "put", "delete", "patch"]:
                if "security" not in path_item[method]:
                    path_item[method]["security"] = [{"Bearer": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Add user info endpoint for React auth context
@app.get("/api/auth/me")
async def get_current_user(user_context: CurrentUserWithACLMap):
    """Get current user information for React auth context"""
    return {
        "username": user_context.get("username"),
        "auth_method": user_context.get("auth_method", "basic"),
        "provider": user_context.get("provider"),
        "scopes": user_context.get("scopes", []),
        "groups": user_context.get("groups", []),
        "can_modify_servers": user_context.get("can_modify_servers", False),
        "is_admin": user_context.get("is_admin", False),
        "user_id": user_context.get("user_id"),
        "acl_permission_map": user_context.get("acl_permission_map", {})
    }


# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "healthy", "service": "mcp-gateway-registry"}


# Version endpoint for UI
@app.get("/api/version")
async def get_version():
    """Get application version."""
    return {"version": __version__}


app.include_router(proxy_router, prefix="/proxy", tags=["MCP Proxy"])

if __name__ == "__main__":
    import uvicorn
    import os

    log_level = os.getenv("LOG_LEVEL", "INFO").lower()

    uvicorn.run(
        "registry.main:app",
        host="0.0.0.0",
        port=7860,
        reload=True,
        log_level=log_level
    )
