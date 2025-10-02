"""Tests for metrics processing logic."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.processor import MetricsProcessor, ProcessingResult
from app.core.models import MetricType, Metric, MetricRequest
from datetime import datetime


class TestProcessingResult:
    """Test ProcessingResult class."""
    
    def test_processing_result_initialization(self):
        """Test ProcessingResult initializes correctly."""
        result = ProcessingResult()
        assert result.accepted == 0
        assert result.rejected == 0
        assert result.errors == []
    
    def test_processing_result_modification(self):
        """Test ProcessingResult can be modified."""
        result = ProcessingResult()
        result.accepted = 5
        result.rejected = 2
        result.errors = ["error1", "error2"]
        
        assert result.accepted == 5
        assert result.rejected == 2
        assert len(result.errors) == 2


class TestMetricsProcessor:
    """Test MetricsProcessor class."""
    
    @patch('app.core.processor.MetricsStorage')
    def test_processor_initialization(self, mock_storage_class):
        """Test processor initializes correctly."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        assert processor.storage is not None
        assert processor._buffer == []
        assert processor._buffer_lock is not None
    
    @patch('app.core.processor.MetricsStorage')
    def test_processor_initialization_with_otel(self, mock_storage_class):
        """Test processor initialization with OpenTelemetry."""
        with patch('app.core.processor.MetricsInstruments') as mock_otel_class:
            mock_otel = MagicMock()
            mock_otel_class.return_value = mock_otel
            
            processor = MetricsProcessor()
            assert processor.otel is not None
    
    @patch('app.core.processor.MetricsStorage')
    def test_processor_initialization_without_otel(self, mock_storage_class):
        """Test processor initialization when OTel is not available."""
        with patch('app.core.processor.MetricsInstruments', side_effect=ImportError()):
            processor = MetricsProcessor()
            assert processor.otel is None


class TestMetricValidation:
    """Test metric validation logic."""
    
    @patch('app.core.processor.MetricsStorage')
    def test_validate_valid_metric(self, mock_storage_class):
        """Test validation of valid metric."""
        processor = MetricsProcessor()
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0
        )
        
        assert processor._validate_metric(metric) is True
    
    @patch('app.core.processor.MetricsStorage')
    def test_validate_metric_with_null_value(self, mock_storage_class):
        """Test validation of metric with null value."""
        processor = MetricsProcessor()
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=None,  # Invalid
            duration_ms=100.0
        )
        
        assert processor._validate_metric(metric) is False
    
    @patch('app.core.processor.MetricsStorage')
    def test_validate_metric_with_zero_value(self, mock_storage_class):
        """Test validation of metric with zero value."""
        processor = MetricsProcessor()
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=0.0,  # Valid
            duration_ms=100.0
        )
        
        assert processor._validate_metric(metric) is True


class TestMetricsProcessing:
    """Test metrics processing logic."""
    
    @patch('app.core.processor.MetricsStorage')
    async def test_process_single_valid_metric(self, mock_storage_class):
        """Test processing a single valid metric."""
        mock_storage = AsyncMock()
        mock_storage.store_metrics_batch = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        processor.otel = None  # Disable OTel for this test
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[metric]
        )
        
        result = await processor.process_metrics(request, "test_req_123", "test-service")
        
        assert result.accepted == 1
        assert result.rejected == 0
        assert len(result.errors) == 0
    
    @patch('app.core.processor.MetricsStorage')
    async def test_process_invalid_metric(self, mock_storage_class):
        """Test processing an invalid metric."""
        mock_storage = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        processor.otel = None
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=None,  # Invalid
            duration_ms=100.0
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[metric]
        )
        
        result = await processor.process_metrics(request, "test_req_123", "test-service")
        
        assert result.accepted == 0
        assert result.rejected == 1
        assert len(result.errors) == 1
        assert "Invalid metric" in result.errors[0]
    
    @patch('app.core.processor.MetricsStorage')
    async def test_process_mixed_valid_invalid_metrics(self, mock_storage_class):
        """Test processing a mix of valid and invalid metrics."""
        mock_storage = AsyncMock()
        mock_storage.store_metrics_batch = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        processor.otel = None
        
        valid_metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0
        )
        
        invalid_metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=None,  # Invalid
            duration_ms=100.0
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[valid_metric, invalid_metric]
        )
        
        result = await processor.process_metrics(request, "test_req_123", "test-service")
        
        assert result.accepted == 1
        assert result.rejected == 1
        assert len(result.errors) == 1
    
    @patch('app.core.processor.MetricsStorage')
    async def test_process_metrics_with_otel_emission(self, mock_storage_class):
        """Test processing metrics with OpenTelemetry emission."""
        mock_storage = AsyncMock()
        mock_storage.store_metrics_batch = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        # Mock OTel instruments
        processor.otel = MagicMock()
        processor.otel.auth_counter = MagicMock()
        processor.otel.auth_histogram = MagicMock()
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0,
            dimensions={"success": True, "method": "jwt"}
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[metric]
        )
        
        result = await processor.process_metrics(request, "test_req_123", "test-service")
        
        assert result.accepted == 1
        assert result.rejected == 0
        
        # Verify OTel methods were called
        processor.otel.auth_counter.add.assert_called_once()
        processor.otel.auth_histogram.record.assert_called_once()
    
    @patch('app.core.processor.MetricsStorage')
    async def test_process_metrics_storage_error(self, mock_storage_class):
        """Test processing metrics when storage fails."""
        mock_storage = AsyncMock()
        mock_storage.store_metrics_batch = AsyncMock(side_effect=Exception("Storage error"))
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        processor.otel = None
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[metric]
        )
        
        result = await processor.process_metrics(request, "test_req_123", "test-service")
        
        assert result.accepted == 0
        assert result.rejected == 1
        assert len(result.errors) == 1
        assert "Error processing metric" in result.errors[0]


class TestOTelEmission:
    """Test OpenTelemetry emission logic."""
    
    @patch('app.core.processor.MetricsStorage')
    async def test_emit_auth_metric_to_otel(self, mock_storage_class):
        """Test emitting auth metric to OpenTelemetry."""
        processor = MetricsProcessor()
        processor.otel = MagicMock()
        processor.otel.auth_counter = MagicMock()
        processor.otel.auth_histogram = MagicMock()
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=150.0,
            dimensions={"success": True, "method": "oauth"}
        )
        
        await processor._emit_to_otel(metric, "test-service")
        
        # Verify counter was called
        processor.otel.auth_counter.add.assert_called_once_with(
            1.0, 
            {
                "service": "test-service",
                "metric_type": "auth_request", 
                "success": "True",
                "method": "oauth"
            }
        )
        
        # Verify histogram was called (duration converted to seconds)
        processor.otel.auth_histogram.record.assert_called_once_with(
            0.15,  # 150ms converted to seconds
            {
                "service": "test-service",
                "metric_type": "auth_request",
                "success": "True", 
                "method": "oauth"
            }
        )
    
    @patch('app.core.processor.MetricsStorage')
    async def test_emit_discovery_metric_to_otel(self, mock_storage_class):
        """Test emitting discovery metric to OpenTelemetry."""
        processor = MetricsProcessor()
        processor.otel = MagicMock()
        processor.otel.discovery_counter = MagicMock()
        processor.otel.discovery_histogram = MagicMock()
        
        metric = Metric(
            type=MetricType.TOOL_DISCOVERY,
            value=1.0,
            duration_ms=50.0,
            dimensions={"query": "test search"}
        )
        
        await processor._emit_to_otel(metric, "registry-service")
        
        processor.otel.discovery_counter.add.assert_called_once()
        processor.otel.discovery_histogram.record.assert_called_once()
    
    @patch('app.core.processor.MetricsStorage')
    async def test_emit_tool_metric_to_otel(self, mock_storage_class):
        """Test emitting tool execution metric to OpenTelemetry."""
        processor = MetricsProcessor()
        processor.otel = MagicMock()
        processor.otel.tool_counter = MagicMock()
        processor.otel.tool_histogram = MagicMock()
        
        metric = Metric(
            type=MetricType.TOOL_EXECUTION,
            value=1.0,
            duration_ms=250.0,
            dimensions={"tool_name": "calculator", "success": True}
        )
        
        await processor._emit_to_otel(metric, "mcpgw-service")
        
        processor.otel.tool_counter.add.assert_called_once()
        processor.otel.tool_histogram.record.assert_called_once()
    
    @patch('app.core.processor.MetricsStorage') 
    async def test_emit_without_otel(self, mock_storage_class):
        """Test emission when OTel is not available."""
        processor = MetricsProcessor()
        processor.otel = None
        
        metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0
        )
        
        # Should not raise any exceptions
        await processor._emit_to_otel(metric, "test-service")


class TestBufferedStorage:
    """Test buffered storage logic."""
    
    @patch('app.core.processor.MetricsStorage')
    async def test_buffer_for_storage(self, mock_storage_class):
        """Test buffering metrics for storage."""
        mock_storage = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        
        metric = Metric(type=MetricType.AUTH_REQUEST, value=1.0)
        request = MetricRequest(service="test", metrics=[metric])
        
        await processor._buffer_for_storage(metric, request, "req_123")
        
        assert len(processor._buffer) == 1
        assert processor._buffer[0]['metric'] == metric
        assert processor._buffer[0]['request'] == request
        assert processor._buffer[0]['request_id'] == "req_123"
    
    @patch('app.core.processor.MetricsStorage')
    async def test_force_flush(self, mock_storage_class):
        """Test force flushing buffered metrics."""
        mock_storage = AsyncMock()
        mock_storage.store_metrics_batch = AsyncMock()
        mock_storage_class.return_value = mock_storage
        
        processor = MetricsProcessor()
        
        # Add some metrics to buffer
        metric = Metric(type=MetricType.AUTH_REQUEST, value=1.0)
        request = MetricRequest(service="test", metrics=[metric])
        processor._buffer = [
            {'metric': metric, 'request': request, 'request_id': 'req_1'},
            {'metric': metric, 'request': request, 'request_id': 'req_2'}
        ]
        
        await processor.force_flush()
        
        # Buffer should be cleared after flush
        assert len(processor._buffer) == 0
        
        # Storage should have been called
        mock_storage.store_metrics_batch.assert_called_once()