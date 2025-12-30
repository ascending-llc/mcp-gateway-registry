"""
MongoDB Connection Pool and Beanie ODM Initialization

This module provides MongoDB connection management with connection pooling
and Beanie ODM initialization for the MCP Gateway Registry.
"""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
from urllib.parse import quote_plus
from packages.models._generated import (
    IAccessRole,
    IAclEntry,
    IAction,
    IGroup,
    MCPServerDocument,
    IUser,
    Token
)



class MongoDB:
    """MongoDB connection manager with connection pooling."""
    client: Optional[AsyncIOMotorClient] = None

    @classmethod
    async def connect_db(cls, mongodb_url: Optional[str] = None, db_name: Optional[str] = None):
        """
        Initialize MongoDB connection with connection pooling.
        
        Args:
            mongodb_url: MongoDB connection URL. If not provided, reads from MONGODB_URL env var.
            db_name: Database name. If not provided, uses default or MONGODB_DB_NAME env var.
        """
        if cls.client is not None:
            return
        # Get MongoDB configuration from environment variables
        if mongodb_url is None:
            # Try to get MONGO_URI first (format: mongodb://host:port/dbname)
            mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/jarvis")
            mongo_username = os.getenv("MONGODB_USERNAME", "")
            mongo_password = os.getenv("MONGODB_PASSWORD", "")
            # Parse MONGO_URI to extract db_name if present
            # Extract database name from URI
            uri_parts = mongo_uri.rsplit('/', 1)
            base_uri = uri_parts[0]
            extracted_db = uri_parts[1] if len(uri_parts) > 1 else None
            if extracted_db and not db_name:
                db_name = extracted_db
            # Insert credentials if provided
            if mongo_username and mongo_password:
                escaped_username = quote_plus(mongo_username)
                escaped_password = quote_plus(mongo_password)
                # Insert credentials after mongodb://
                protocol, rest = base_uri.split('://', 1)
                mongodb_url = f"{protocol}://{escaped_username}:{escaped_password}@{rest}"
            else:
                mongodb_url = base_uri
        cls.database_name = db_name
        try:
            # Create Motor client with connection pool settings
            cls.client = AsyncIOMotorClient(
                mongodb_url,
                maxPoolSize=50,  # Maximum number of connections in the pool
                minPoolSize=10,  # Minimum number of connections in the pool
                maxIdleTimeMS=30000,  # Close connections after 30 seconds of inactivity
                waitQueueTimeoutMS=5000,  # Wait up to 5 seconds for a connection from pool
                connectTimeoutMS=10000,  # Connection timeout
                serverSelectionTimeoutMS=10000,  # Server selection timeout
                retryWrites=True,  # Retry write operations
                retryReads=True,  # Retry read operations
            )
            # Verify connection
            await cls.client.admin.command('ping')
            # Get database
            db = cls.client[db_name]
            # Pass the namespace containing all model classes so forward references can be resolved
            rebuild_namespace = {
                "IUser": IUser,
                "IAccessRole": IAccessRole,
                "IGroup": IGroup,
                "IAclEntry": IAclEntry,
                "MCPServerDocument": MCPServerDocument,
                "Token": Token,
                "IAction": IAction,
            }
            MCPServerDocument.model_rebuild(_types_namespace=rebuild_namespace)
            Token.model_rebuild(_types_namespace=rebuild_namespace)
            IAclEntry.model_rebuild(_types_namespace=rebuild_namespace)
            IAction.model_rebuild(_types_namespace=rebuild_namespace)

            # Initialize Beanie with all document models
            await init_beanie(
                database=db,
                document_models=[
                    IUser,
                    MCPServerDocument,
                    IAccessRole,
                    IAclEntry,
                    IGroup,
                    Token,
                    IAction,
                ]
            )
        except Exception as e:
            raise

    @classmethod
    async def close_db(cls):
        """Close MongoDB connection and cleanup resources."""
        if cls.client is None:
            return

        try:
            cls.client.close()
            cls.client = None
        except Exception as e:
            raise

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        """
        Get the MongoDB client instance.
        
        Returns:
            AsyncIOMotorClient: The Motor client instance.
            
        Raises:
            RuntimeError: If the database connection is not initialized.
        """
        if cls.client is None:
            raise RuntimeError(
                "Database connection is not initialized. "
                "Call MongoDB.connect_db() first."
            )
        return cls.client

    @classmethod
    def get_database(cls):
        """
        Get the MongoDB database instance.
        
        Returns:
            Database: The Motor database instance.
            
        Raises:
            RuntimeError: If the database connection is not initialized.
        """
        if cls.client is None:
            raise RuntimeError(
                "Database connection is not initialized. "
                "Call MongoDB.connect_db() first."
            )
        return cls.client[cls.database_name]


# Convenience functions for FastAPI lifespan events
async def init_mongodb(mongodb_url: Optional[str] = None, db_name: Optional[str] = None):
    """
    Initialize MongoDB connection. To be called during FastAPI startup.
    
    Args:
        mongodb_url: MongoDB connection URL
        db_name: Database name
    """
    await MongoDB.connect_db(mongodb_url, db_name)


async def close_mongodb():
    """
    Close MongoDB connection. To be called during FastAPI shutdown.
    """
    await MongoDB.close_db()
