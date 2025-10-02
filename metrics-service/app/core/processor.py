import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from ..core.models import MetricRequest, Metric, MetricType
from ..storage.database import MetricsStorage
from ..core.validator import validator

logger = logging.getLogger(__name__)


class ProcessingResult:
    def __init__(self):
        self.accepted = 0
        self.rejected = 0
        self.errors = []


class MetricsProcessor:
    """Core metrics processing engine."""
    
    def __init__(self):
        self.storage = MetricsStorage()
        self._buffer = []
        self._buffer_lock = asyncio.Lock()
        
        # Try to initialize OTel instruments, but don't fail if it doesn't work
        self.otel = None
        try:
            from ..otel.instruments import MetricsInstruments
            self.otel = MetricsInstruments()
            logger.info("OpenTelemetry instruments initialized")
        except Exception as e:
            logger.warning(f"OpenTelemetry instruments not available: {e}")
        
    async def process_metrics(
        self, 
        request: MetricRequest, 
        request_id: str, 
        api_key: str
    ) -> ProcessingResult:
        """Process incoming metrics request."""
        result = ProcessingResult()
        
        # Validate the entire request first
        validation_result = validator.validate_metric_request(request)
        if not validation_result.is_valid:
            result.rejected = len(request.metrics)
            result.errors.extend(validation_result.get_error_messages())
            return result
        
        # Log any validation warnings
        for warning in validation_result.warnings:
            logger.warning(f"Metrics validation warning: {warning}")
        
        for metric in request.metrics:
            try:
                # Additional runtime validation
                if not self._validate_metric(metric):
                    result.rejected += 1
                    result.errors.append(f"Invalid metric: {metric.type}")
                    continue
                
                # Emit to OpenTelemetry if available
                if self.otel:
                    try:
                        await self._emit_to_otel(metric, request.service)
                    except Exception as e:
                        logger.warning(f"Failed to emit to OTel: {e}")
                
                # Store in SQLite (buffered)
                await self._buffer_for_storage(
                    metric, request, request_id
                )
                
                result.accepted += 1
                
            except Exception as e:
                result.rejected += 1
                result.errors.append(f"Error processing metric: {str(e)}")
                logger.error(f"Error processing metric: {e}")
        
        return result
    
    def _validate_metric(self, metric: Metric) -> bool:
        """Validate metric data."""
        if metric.value is None:
            return False
        if metric.type not in MetricType:
            return False
        return True
    
    async def _emit_to_otel(self, metric: Metric, service: str):
        """Emit metric to OpenTelemetry instruments."""
        if not self.otel:
            return
            
        labels = {
            "service": service,
            "metric_type": metric.type.value,
            **{k: str(v) for k, v in metric.dimensions.items()}
        }
        
        # Route to appropriate OTel instrument
        if metric.type == MetricType.AUTH_REQUEST:
            self.otel.auth_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.auth_histogram.record(metric.duration_ms / 1000, labels)
                
        elif metric.type == MetricType.TOOL_DISCOVERY:
            self.otel.discovery_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.discovery_histogram.record(metric.duration_ms / 1000, labels)
                
        elif metric.type == MetricType.TOOL_EXECUTION:
            self.otel.tool_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.tool_histogram.record(metric.duration_ms / 1000, labels)

        elif metric.type == MetricType.PROTOCOL_LATENCY:
            # For protocol latency, record the value as latency seconds
            self.otel.latency_histogram.record(metric.value, labels)

        elif metric.type == MetricType.HEALTH_CHECK:
            self.otel.health_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.health_histogram.record(metric.duration_ms / 1000, labels)
    
    async def _buffer_for_storage(
        self, 
        metric: Metric, 
        request: MetricRequest, 
        request_id: str
    ):
        """Buffer metric for batch SQLite storage."""
        async with self._buffer_lock:
            self._buffer.append({
                'metric': metric,
                'request': request,
                'request_id': request_id
            })
            
            # Flush buffer if it's full
            if len(self._buffer) >= 100:
                await self._flush_buffer()
    
    async def _flush_buffer(self):
        """Flush buffered metrics to SQLite."""
        if not self._buffer:
            return
            
        buffer_copy = self._buffer.copy()
        self._buffer.clear()
        
        try:
            await self.storage.store_metrics_batch(buffer_copy)
            logger.debug(f"Flushed {len(buffer_copy)} metrics to storage")
        except Exception as e:
            logger.error(f"Failed to flush metrics buffer: {e}")
            # Re-add to buffer for retry
            self._buffer.extend(buffer_copy)
    
    async def force_flush(self):
        """Force flush all buffered metrics."""
        async with self._buffer_lock:
            await self._flush_buffer()