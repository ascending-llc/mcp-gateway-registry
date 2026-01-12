import os
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider, Meter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from prometheus_client import start_http_server
import logging

# Try to import settings, but don't crash if used in a standalone script
try:
    from ..config import settings
except ImportError:
    settings = None

logger = logging.getLogger(__name__)

def setup_otel(
    service_name: str = None,
    prometheus_enabled: bool = None,
    prometheus_port: int = None,
    otlp_endpoint: str = None
) -> Meter:
    """
    Setup OpenTelemetry metric providers and exporters.
    Safe to call in different services; returns a Meter instance.
    """
    
    # --- 1. Resolve Configuration ---
    
    # Service Name
    cfg_service_name = service_name or \
                       getattr(settings, 'OTEL_SERVICE_NAME', None) or \
                       os.getenv('OTEL_SERVICE_NAME', 'unknown-service')
    
    # Prometheus Enabled
    if prometheus_enabled is not None:
        cfg_prom_enabled = prometheus_enabled
        prom_source = "Argument"
    else:
        # Check settings, then check raw env var
        val_settings = getattr(settings, 'OTEL_PROMETHEUS_ENABLED', None)
        val_env = os.getenv('OTEL_PROMETHEUS_ENABLED', 'false')
        
        if val_settings is not None:
            cfg_prom_enabled = val_settings
            prom_source = "Settings (Config)"
        else:
            cfg_prom_enabled = str(val_env).lower() == 'true'
            prom_source = f"EnvVar (Raw value: '{val_env}')"
    
    # Prometheus Port
    if prometheus_port:
        cfg_prom_port = prometheus_port
    else:
        cfg_prom_port = getattr(settings, 'OTEL_PROMETHEUS_PORT', None) or \
                        int(os.getenv('OTEL_PROMETHEUS_PORT', 9464))
    
    # OTLP Endpoint
    cfg_otlp_endpoint = otlp_endpoint or \
                        getattr(settings, 'OTEL_OTLP_ENDPOINT', None) or \
                        os.getenv('OTEL_OTLP_ENDPOINT', None)

    # --- 2. Log Resolved Configuration ---
    logger.info("🔭 OpenTelemetry Configuration Resolution:")
    logger.info(f"   - Service Name:      {cfg_service_name}")
    logger.info(f"   - Prometheus:        {cfg_prom_enabled} (Source: {prom_source})")
    logger.info(f"   - Prometheus Port:   {cfg_prom_port}")
    logger.info(f"   - OTLP Endpoint:     {cfg_otlp_endpoint or 'Disabled'}")

    # --- 3. Check for Existing Provider ---
    current_provider = metrics.get_meter_provider()
    if isinstance(current_provider, MeterProvider):
        logger.info(f"⚠️ OpenTelemetry MeterProvider already initialized. Skipping setup for {cfg_service_name}.")
        return metrics.get_meter(cfg_service_name)

    readers = []
    
    try:
        resource = Resource.create(attributes={
            SERVICE_NAME: cfg_service_name
        })
        
        # --- 4. Setup Prometheus ---
        if cfg_prom_enabled:
            logger.info(f"Attempting to start Prometheus server on port {cfg_prom_port}...")
            try:
                # Check if port is actually open before trying to bind (optional double-check)
                start_http_server(port=cfg_prom_port, addr="0.0.0.0")
                
                reader = PrometheusMetricReader()
                readers.append(reader)
                logger.info(f"✅ Prometheus metrics server started successfully on port {cfg_prom_port}")
                
            except OSError as e:
                if e.errno == 98: # Address already in use
                    logger.warning(f"⚠️ Port {cfg_prom_port} is already in use. Prometheus metrics might already be running.")
                    # We still add the reader because the server might have been started by another part of the app
                    readers.append(PrometheusMetricReader())
                else:
                    logger.error(f"❌ Failed to start Prometheus server: {e}")
                    raise e
        else:
            logger.info("Prometheus exporter is DISABLED.")

        # --- 5. Setup OTLP ---
        if cfg_otlp_endpoint:
            logger.info(f"Configuring OTLP exporter to {cfg_otlp_endpoint}...")
            otlp_exporter = OTLPMetricExporter(endpoint=f"{cfg_otlp_endpoint}/v1/metrics")
            otlp_reader = PeriodicExportingMetricReader(
                exporter=otlp_exporter,
                export_interval_millis=30000
            )
            readers.append(otlp_reader)
            logger.info(f"✅ OTLP exporter enabled.")
        
        # --- 6. Finalize Provider ---
        if readers:
            meter_provider = MeterProvider(
                resource=resource,
                metric_readers=readers
            )
            metrics.set_meter_provider(meter_provider)
            logger.info(f"✨ OpenTelemetry successfully configured for {cfg_service_name} with {len(readers)} readers.")
        else:
            logger.warning("⚠️ No OpenTelemetry exporters configured; metrics will be no-op.")
            
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to setup OpenTelemetry: {e}", exc_info=True)
    
    return metrics.get_meter(cfg_service_name)