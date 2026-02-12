"""
Tests for packages/telemetry/decorators.py

Tests for generic telemetry decorators that provide automatic timing
and metrics collection.
"""

import asyncio

import pytest

from registry_pkgs.telemetry.decorators import (
    _safe_extract_labels,
    create_timed_context,
    track_duration,
)


@pytest.mark.unit
@pytest.mark.metrics
class TestSafeExtractLabels:
    """Test suite for _safe_extract_labels helper function."""

    def test_returns_empty_dict_when_no_extractor(self):
        """Test returns empty dict when extract_labels is None."""
        result = _safe_extract_labels(None, (), {})
        assert result == {}

    def test_extracts_labels_from_args(self):
        """Test extracts labels using provided function."""

        def extractor(*args, **kwargs):
            return {"arg0": args[0], "kwarg": kwargs.get("key", "default")}

        result = _safe_extract_labels(extractor, ("value1",), {"key": "value2"})
        assert result == {"arg0": "value1", "kwarg": "value2"}

    def test_converts_values_to_strings(self):
        """Test converts all label values to strings."""

        def extractor(*args, **kwargs):
            return {"int_val": 42, "bool_val": True}

        result = _safe_extract_labels(extractor, (), {})
        assert result == {"int_val": "42", "bool_val": "True"}

    def test_returns_empty_dict_on_extractor_error(self):
        """Test returns empty dict when extractor raises exception."""

        def failing_extractor(*args, **kwargs):
            raise ValueError("Extraction failed")

        result = _safe_extract_labels(failing_extractor, (), {})
        assert result == {}

    def test_handles_result_parameter(self):
        """Test passes result to extractor when provided."""

        def extractor(*args, result=None, **kwargs):
            return {"result_type": type(result).__name__}

        result = _safe_extract_labels(extractor, (), {}, result={"data": "test"})
        assert result == {"result_type": "dict"}

    def test_handles_error_parameter(self):
        """Test passes error to extractor when provided."""

        def extractor(*args, error=None, **kwargs):
            return {"has_error": str(error is not None)}

        result = _safe_extract_labels(extractor, (), {}, error=ValueError("test"))
        assert result == {"has_error": "True"}


@pytest.mark.unit
@pytest.mark.metrics
class TestTrackDurationDecorator:
    """Test suite for track_duration decorator."""

    @pytest.mark.asyncio
    async def test_tracks_async_function_duration(self):
        """Test decorator tracks duration of async functions."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        @track_duration(record_func)
        async def async_operation():
            await asyncio.sleep(0.01)
            return "result"

        result = await async_operation()

        assert result == "result"
        assert len(recorded_calls) == 1
        duration, labels = recorded_calls[0]
        assert duration > 0.01
        assert labels["success"] == "true"

    def test_tracks_sync_function_duration(self):
        """Test decorator tracks duration of sync functions."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        @track_duration(record_func)
        def sync_operation():
            return "result"

        result = sync_operation()

        assert result == "result"
        assert len(recorded_calls) == 1
        duration, labels = recorded_calls[0]
        assert duration >= 0
        assert labels["success"] == "true"

    @pytest.mark.asyncio
    async def test_tracks_async_function_failure(self):
        """Test decorator tracks failure of async functions."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        @track_duration(record_func)
        async def failing_operation():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await failing_operation()

        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert labels["success"] == "false"

    def test_tracks_sync_function_failure(self):
        """Test decorator tracks failure of sync functions."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        @track_duration(record_func)
        def failing_operation():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_operation()

        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert labels["success"] == "false"

    @pytest.mark.asyncio
    async def test_extracts_labels_from_args(self):
        """Test decorator extracts labels using provided function."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        def extract_labels(name, **kwargs):
            return {"operation_name": name}

        @track_duration(record_func, extract_labels=extract_labels)
        async def named_operation(name):
            return f"Hello, {name}"

        result = await named_operation("test")

        assert result == "Hello, test"
        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert labels["operation_name"] == "test"
        assert labels["success"] == "true"

    @pytest.mark.asyncio
    async def test_can_disable_success_label(self):
        """Test decorator can disable automatic success label."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        @track_duration(record_func, include_success=False)
        async def operation():
            return "result"

        await operation()

        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert "success" not in labels

    @pytest.mark.asyncio
    async def test_handles_record_func_error_gracefully(self):
        """Test decorator handles errors in record_func gracefully."""

        def failing_record_func(duration, labels):
            raise RuntimeError("Recording failed")

        @track_duration(failing_record_func)
        async def operation():
            return "result"

        # Should not raise, should complete successfully
        result = await operation()
        assert result == "result"

    def test_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        def record_func(duration, labels):
            pass

        @track_duration(record_func)
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


@pytest.mark.unit
@pytest.mark.metrics
class TestTimedContext:
    """Test suite for create_timed_context context manager."""

    @pytest.mark.asyncio
    async def test_records_duration_on_exit(self):
        """Test context manager records duration when exiting."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        async with create_timed_context(record_func):
            await asyncio.sleep(0.01)

        assert len(recorded_calls) == 1
        duration, labels = recorded_calls[0]
        assert duration >= 0.01
        assert labels["success"] == "true"

    @pytest.mark.asyncio
    async def test_records_failure_on_exception(self):
        """Test context manager records failure when exception occurs."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        with pytest.raises(ValueError):
            async with create_timed_context(record_func):
                raise ValueError("Test error")

        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert labels["success"] == "false"

    @pytest.mark.asyncio
    async def test_can_set_success_manually(self):
        """Test context manager allows manual success setting."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        async with create_timed_context(record_func) as ctx:
            ctx.set_success(False)

        _, labels = recorded_calls[0]
        assert labels["success"] == "false"

    @pytest.mark.asyncio
    async def test_can_add_labels(self):
        """Test context manager allows adding labels."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        async with create_timed_context(record_func) as ctx:
            ctx.add_label("operation", "test")
            ctx.add_label("resource", "server")

        _, labels = recorded_calls[0]
        assert labels["operation"] == "test"
        assert labels["resource"] == "server"

    @pytest.mark.asyncio
    async def test_includes_initial_labels(self):
        """Test context manager includes labels passed at creation."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        async with create_timed_context(record_func, labels={"env": "test"}):
            pass

        _, labels = recorded_calls[0]
        assert labels["env"] == "test"
        assert labels["success"] == "true"

    def test_works_with_sync_context(self):
        """Test context manager works in sync context."""
        recorded_calls = []

        def record_func(duration, labels):
            recorded_calls.append((duration, labels))

        with create_timed_context(record_func) as ctx:
            ctx.add_label("sync", "true")

        assert len(recorded_calls) == 1
        _, labels = recorded_calls[0]
        assert labels["sync"] == "true"
        assert labels["success"] == "true"

    @pytest.mark.asyncio
    async def test_handles_record_func_error(self):
        """Test context manager handles record_func errors gracefully."""

        def failing_record_func(duration, labels):
            raise RuntimeError("Recording failed")

        # Should not raise
        async with create_timed_context(failing_record_func):
            pass
