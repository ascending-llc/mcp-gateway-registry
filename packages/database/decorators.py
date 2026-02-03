"""
Decorators for managing database transactions.
"""

import functools
import logging
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import ConnectionFailure, OperationFailure
from packages.database.mongodb import MongoDB
from typing import Optional
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_tx_session: ContextVar[Optional[AsyncClientSession]] = ContextVar("_tx_session", default=None)
def use_transaction(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        existing_session = _tx_session.get()
        if existing_session:
            # Prevent nested transactions
            raise RuntimeError(
                f"Nested transaction detected in {func.__name__}. "
                f"Remove @use_transaction decorator from this function or its callers."
                f"Only apply @use_transaction to route handlers, not service methods."
            )
        
        client: AsyncMongoClient = MongoDB.get_client()
        try:
            async with client.start_session() as session:
                async with await session.start_transaction():
                    token = _tx_session.set(session)
                    try: 
                        return await func(*args, **kwargs)
                    finally: 
                        _tx_session.reset(token)
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
            
    return wrapper

def get_current_session() -> AsyncClientSession:
    session = _tx_session.get()
    if session is None:
        raise RuntimeError("No active transaction. Use @use_transaction decorator.")
    return session   



