import functools
import logging
from pathlib import Path
from typing import (
    Any,
)

import yaml
from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram

logger = logging.getLogger(__name__)


def load_metrics_config(service_name: str, config_path: str | None = None) -> dict | None:
    """
    Load metrics configuration from YAML file for a specific service.

    Args:
        service_name: Name of the service (e.g., 'registry', 'auth_server')
        config_path: Optional path to the config file. If not provided,
                    defaults to standard location relative to this file.

    Returns:
        Configuration dictionary or None if file not found/invalid
    """
    if config_path:
        path = Path(config_path)
    else:
        # Default: config/metrics/{service_name}.yml relative to project root
        # derived from this file's location: packages/telemetry/metrics_client.py
        path = Path(__file__).parent.parent.parent / "config" / "metrics" / f"{service_name}.yml"

    if not path.exists():
        logger.debug(f"Metrics config not found at {path}, using defaults")
        return None

    try:
        with open(path) as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded metrics config from {path}")
            return config
    except Exception as e:
        logger.warning(f"Failed to load metrics config for {service_name} from {path}: {e}")
        return None


def safe_telemetry(func):
    """
    Decorator to safely execute telemetry methods.
    Swallows exceptions and logs them as warnings to prevent application crashes.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Telemetry error in {func.__name__}: {e}")

    return wrapper


class OTelMetricsClient:
    """
    Generic client for defining and recording OpenTelemetry metrics.
    Safe to use - methods swallow exceptions to prevent application crashes.

    This client provides generic metric operations:
    - create_counter(), create_histogram() - Define metrics
    - record_counter(), record_histogram() - Record values
    - record_metric() - Auto-detect metric type and record

    Domain-specific recording logic should be implemented in service-specific
    modules (e.g., registry/utils/otel_metrics.py) to keep this package
    decoupled from business logic.
    """

    def __init__(
        self,
        service_name: str,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize metrics client for a specific service.

        All metrics are loaded from the config dict. The config should define
        counters and histograms that the service needs.

        Args:
            service_name: Name of the service (e.g., 'api', 'worker', 'registry')
            config: Configuration dict with 'counters' and 'histograms' lists
        """
        try:
            self.service_name = service_name
            self.meter = metrics.get_meter(f"mcp.{service_name}")

            # Dynamic metric registries - all metrics loaded from config
            self._counters: dict[str, Counter] = {}
            self._histograms: dict[str, Histogram] = {}

            # Initialize from config
            if config:
                self._init_from_config(config)

        except Exception as e:
            logger.error(f"Failed to initialize OTelMetricsClient for service '{service_name}': {e}")

    def _init_from_config(self, config: dict[str, Any]) -> None:
        """
        Initialize metrics from configuration dictionary.

        Config format:
            {
                "counters": [
                    {"name": "my_counter", "description": "...", "unit": "1", "capture": true}
                ],
                "histograms": [
                    {"name": "my_histogram", "description": "...", "unit": "s", "capture": true}
                ]
            }

        The 'capture' flag controls whether the metric is registered:
        - capture: true (default) - metric is registered and will record data
        - capture: false - metric is skipped, calls to record will be no-ops
        """
        for counter_def in config.get("counters", []):
            # Skip if capture is explicitly set to false
            if not counter_def.get("capture", True):
                logger.debug(f"Skipping counter '{counter_def['name']}' (capture=false)")
                continue

            self.create_counter(
                name=counter_def["name"],
                description=counter_def.get("description", ""),
                unit=counter_def.get("unit", "1"),
            )

        for histogram_def in config.get("histograms", []):
            # Skip if capture is explicitly set to false
            if not histogram_def.get("capture", True):
                logger.debug(f"Skipping histogram '{histogram_def['name']}' (capture=false)")
                continue

            self.create_histogram(
                name=histogram_def["name"],
                description=histogram_def.get("description", ""),
                unit=histogram_def.get("unit", "s"),
            )

    @safe_telemetry
    def create_counter(
        self,
        name: str,
        description: str = "",
        unit: str = "1",
    ) -> Counter | None:
        """
        Dynamically create and register a counter metric.

        Args:
            name: Metric name (e.g., "requests_total")
            description: Human-readable description
            unit: Unit of measurement (default: "1" for counts)

        Returns:
            The created Counter instance, or None if creation failed
        """
        if name not in self._counters:
            counter = self.meter.create_counter(
                name=name,
                description=description,
                unit=unit,
            )
            self._counters[name] = counter
        return self._counters.get(name)

    @safe_telemetry
    def create_histogram(
        self,
        name: str,
        description: str = "",
        unit: str = "s",
    ) -> Histogram | None:
        """
        Dynamically create and register a histogram metric.

        Args:
            name: Metric name (e.g., "request_duration_seconds")
            description: Human-readable description
            unit: Unit of measurement (default: "s" for seconds)

        Returns:
            The created Histogram instance, or None if creation failed
        """
        if name not in self._histograms:
            histogram = self.meter.create_histogram(
                name=name,
                description=description,
                unit=unit,
            )
            self._histograms[name] = histogram
        return self._histograms.get(name)

    @safe_telemetry
    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """
        Record a value to a counter metric.

        Args:
            name: Name of the counter metric
            value: Value to add (default: 1.0)
            attributes: Optional dictionary of label key-value pairs
        """
        counter = self._counters.get(name)
        if counter:
            counter.add(value, attributes or {})
        else:
            logger.warning(f"Counter '{name}' not registered")

    @safe_telemetry
    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """
        Record a value to a histogram metric.

        Args:
            name: Name of the histogram metric
            value: Value to record (e.g., duration in seconds)
            attributes: Optional dictionary of label key-value pairs
        """
        histogram = self._histograms.get(name)
        if histogram:
            histogram.record(value, attributes or {})
        else:
            logger.warning(f"Histogram '{name}' not registered")

    @safe_telemetry
    def record_metric(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """
        Generic method to record any metric by name.

        Automatically detects whether the metric is a counter or histogram
        and records the value appropriately.

        Args:
            name: Name of the metric (counter or histogram)
            value: Value to record
            attributes: Optional dictionary of label key-value pairs
        """
        attributes = attributes or {}

        if name in self._counters:
            self._counters[name].add(value, attributes)
        elif name in self._histograms:
            self._histograms[name].record(value, attributes)
        else:
            logger.warning(f"Metric '{name}' not registered as counter or histogram")

    def get_counter(self, name: str) -> Counter | None:
        """Get a registered counter by name."""
        return self._counters.get(name)

    def get_histogram(self, name: str) -> Histogram | None:
        """Get a registered histogram by name."""
        return self._histograms.get(name)


def create_metrics_client(
    service_name: str,
    config: dict[str, Any] | None = None,
) -> OTelMetricsClient:
    """
    Create a metrics client for a specific service.

    This factory function creates a new OTelMetricsClient instance with
    service-specific meter identity for better observability in dashboards.

    Args:
        service_name: Identifier for the service (e.g., 'api', 'worker', 'registry')
        config: Optional configuration dict with 'counters' and 'histograms' lists

    Returns:
        Configured OTelMetricsClient instance

    Example:
        >>> config = {
        ...     "counters": [{"name": "requests_total", "description": "Total requests"}],
        ...     "histograms": [{"name": "request_duration_seconds", "description": "Request duration"}]
        ... }
        >>> metrics = create_metrics_client("api", config=config)
        >>> metrics.record_counter("requests_total", 1, {"endpoint": "/users"})
        >>> metrics.record_histogram("request_duration_seconds", 0.05, {"endpoint": "/users"})
    """
    return OTelMetricsClient(service_name, config=config)
