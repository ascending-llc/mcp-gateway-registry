"""Tests for MongoDB transaction dependency."""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from pymongo.errors import OperationFailure, ConnectionFailure

from packages.database.transaction import get_tx_session
from packages.database.mongodb import MongoDB


def _make_mock_session():
    """
    Create a mock AsyncClientSession whose start_transaction()
    returns a coroutine that yields an async context manager.
    """
    mock_session = AsyncMock()
    mock_session.end_session = AsyncMock()

    @asynccontextmanager
    async def _transaction_context():
        yield
        # If the body raised, the async with propagates it after __aexit__

    async def _fake_transaction(*args, **kwargs):
        return _transaction_context()

    mock_session.start_transaction = _fake_transaction
    return mock_session


class TestGetTxSession:
    """Tests for the get_tx_session FastAPI dependency."""

    @pytest.fixture(autouse=True)
    def reset_mongodb_state(self):
        """Reset MongoDB class state before each test."""
        self._original_client = MongoDB.client
        yield
        MongoDB.client = self._original_client

    @pytest.mark.asyncio
    async def test_yields_session_with_active_transaction(self):
        """Test that get_tx_session yields a session and commits on success."""
        mock_client = MagicMock()
        mock_session = _make_mock_session()
        mock_client.start_session.return_value = mock_session
        MongoDB.client = mock_client

        gen = get_tx_session()
        session = await gen.__anext__()

        assert session is mock_session
        mock_client.start_session.assert_called_once()

        # Finish the generator (simulates successful endpoint completion)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_closed_on_exception(self):
        """Test that the session is always closed, even on exceptions."""
        mock_client = MagicMock()
        mock_session = _make_mock_session()
        mock_client.start_session.return_value = mock_session
        MongoDB.client = mock_client

        gen = get_tx_session()
        session = await gen.__anext__()
        assert session is mock_session

        # Simulate an exception during endpoint execution
        with pytest.raises(ValueError):
            await gen.athrow(ValueError("test error"))

        mock_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_client_not_initialized(self):
        """Test that RuntimeError is raised when MongoDB client is not initialized."""
        MongoDB.client = None

        with pytest.raises(RuntimeError, match="Database connection is not initialized"):
            gen = get_tx_session()
            await gen.__anext__()

    @pytest.mark.asyncio
    async def test_operation_failure_propagated(self):
        """Test that OperationFailure is properly propagated and session closed."""
        mock_client = MagicMock()
        mock_session = _make_mock_session()
        mock_client.start_session.return_value = mock_session
        MongoDB.client = mock_client

        gen = get_tx_session()
        await gen.__anext__()

        op_error = OperationFailure("transaction not supported", code=263)
        with pytest.raises(OperationFailure):
            await gen.athrow(op_error)

        mock_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_failure_propagated(self):
        """Test that ConnectionFailure is properly propagated and session closed."""
        mock_client = MagicMock()
        mock_session = _make_mock_session()
        mock_client.start_session.return_value = mock_session
        MongoDB.client = mock_client

        gen = get_tx_session()
        await gen.__anext__()

        conn_error = ConnectionFailure("connection lost")
        with pytest.raises(ConnectionFailure):
            await gen.athrow(conn_error)

        mock_session.end_session.assert_called_once()
