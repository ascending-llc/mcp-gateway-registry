"""
Transaction Support for MongoDB with PyMongo Async

Provides a FastAPI dependency that yields an AsyncClientSession
wrapped in a transaction. Requires MongoDB to run as a replica set.
"""

import logging
from typing import AsyncIterator

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import ConnectionFailure, OperationFailure

from packages.database.mongodb import MongoDB

logger = logging.getLogger(__name__)


async def get_tx_session() -> AsyncIterator[AsyncClientSession]:
    """
    FastAPI dependency that provides a transactional MongoDB session.

    Starts a session on the shared AsyncMongoClient, begins a transaction,
    and yields the session. On successful completion the transaction is
    committed automatically by the context manager. On exception the
    transaction is aborted and the error is re-raised.

    Yields:
        AsyncClientSession: A session with an active transaction.

    Raises:
        RuntimeError: If the MongoDB client is not initialized.
        OperationFailure: If the replica set is not configured (error code 263).
    """
    client: AsyncMongoClient = MongoDB.get_client()
    try:
        async with client.start_session() as session:
            async with await session.start_transaction():
                yield session
    except OperationFailure as exc:
        # Provide an actionable message when replica set is missing
        if exc.code == 263 or "transaction" in str(exc).lower():
            logger.error(
                "Transaction failed - MongoDB must run as a replica set. "
                "Start mongod with --replSet rs0 and run rs.initiate(). "
                "See docker-compose.yml for a single-node replica set example. "
                "Original error: %s",
                exc,
            )
        raise
    except ConnectionFailure as exc:
        logger.error("MongoDB connection failure during transaction: %s", exc)
        raise
    except Exception:
        logger.error("Transaction failed due to an unexpected error.", exc_info=True)
        raise
