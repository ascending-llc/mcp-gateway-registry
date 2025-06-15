#!/usr/bin/env python3
"""
MCP Gateway Registry - Modern FastAPI Application

A clean, domain-driven FastAPI app for managing MCP (Model Context Protocol) servers.
This main.py file serves as the application coordinator, importing and registering 
domain routers while handling core app configuration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

# Import domain routers
from registry.auth.routes import router as auth_router
from registry.api.server_routes import router as servers_router
from registry.health.routes import router as health_router

# Import services for initialization
from registry.services.server_service import server_service
from registry.search.service import faiss_service
from registry.health.service import health_service
from registry.core.nginx_service import nginx_service

# Import core configuration
from registry.core.config import settings

# Configure logging with file and console handlers
def setup_logging():
    """Configure logging to write to both file and console."""
    # Ensure log directory exists
    log_dir = settings.container_log_dir
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
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
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
        # Initialize services in order
        logger.info("📚 Loading server definitions and state...")
        server_service.load_servers_and_state()
        
        logger.info("🔍 Initializing FAISS search service...")
        await faiss_service.initialize()
        
        logger.info("🏥 Initializing health monitoring service...")
        await health_service.initialize()
        
        logger.info("🌐 Generating initial Nginx configuration...")
        enabled_servers = {
            path: server_service.get_server_info(path) 
            for path in server_service.get_enabled_services()
        }
        await nginx_service.generate_config_async(enabled_servers)
        
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

# Configure static files and templates
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

# Register domain routers
app.include_router(auth_router, tags=["Authentication"])
app.include_router(servers_router, tags=["Server Management"])
app.include_router(health_router, tags=["Health Monitoring"])

# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "healthy", "service": "mcp-gateway-registry"}





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "registry.main:app", 
        host="0.0.0.0", 
        port=7860, 
        reload=True,
        log_level="info"
    ) 