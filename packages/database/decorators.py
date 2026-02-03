"""
Decorators for managing database transactions.
"""

import functools
import logging
from contextvars import ContextVar
from typing import Any, Callable, Optional

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import ConnectionFailure, OperationFailure

from packages.database.mongodb import MongoDB

logger = logging.getLogger(__name__)

MONGODB_TRANSACTION_NOT_SUPPORTED_ERROR = 263

_tx_session: ContextVar[Optional[AsyncClientSession]] = ContextVar(
    "_tx_session", default=None
)


def use_transaction(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        active_session = _tx_session.get()
        if active_session:
            raise RuntimeError(
                f"Nested transaction detected in {func.__name__}. "
                f"Remove @use_transaction decorator from this function or its callers. "
                f"Only apply @use_transaction to route handlers, not service methods."
            )
        
        client: AsyncMongoClient = MongoDB.get_client()
        try:
            async with client.start_session() as session:
                async with await session.start_transaction():
                    context_token = _tx_session.set(session)
                    try:
                        return await func(*args, **kwargs)
                    finally: 
                        _tx_session.reset(context_token)
        except OperationFailure as exc:
            if exc.code == MONGODB_TRANSACTION_NOT_SUPPORTED_ERROR:
                logger.error(
                    "Transaction failed - MongoDB must run as a replica set. "
                    "Start mongod with --replSet rs0 and run rs.initiate(). "
                    "See docker-compose.yml for a single-node replica set example. "
                    "Original error: %s",
                    exc,
                )
            raise
        except ConnectionFailure as connection_error:
            logger.error(
                "MongoDB connection failure during transaction: %s", connection_error
            )
            raise
        except Exception:
            logger.error(
                "Transaction failed due to an unexpected error.", exc_info=True
            )
            raise
            
    return wrapper


def get_current_session() -> AsyncClientSession:
    session = _tx_session.get()
    if session is None:
        raise RuntimeError("No active transaction. Use @use_transaction decorator.")
    return session   



