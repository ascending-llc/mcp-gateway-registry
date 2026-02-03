import os


class Settings:
    # Database settings
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "/var/lib/sqlite/metrics.db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{SQLITE_DB_PATH}")
    METRICS_RETENTION_DAYS: int = int(os.getenv("METRICS_RETENTION_DAYS", "90"))
    DB_CONNECTION_TIMEOUT: int = int(os.getenv("DB_CONNECTION_TIMEOUT", "30"))
    DB_MAX_RETRIES: int = int(os.getenv("DB_MAX_RETRIES", "5"))

    # Service settings
    METRICS_SERVICE_PORT: int = int(os.getenv("METRICS_SERVICE_PORT", "8890"))
    METRICS_SERVICE_HOST: str = os.getenv("METRICS_SERVICE_HOST", "0.0.0.0")

    # OpenTelemetry settings
    OTEL_SERVICE_NAME: str = os.getenv("OTEL_SERVICE_NAME", "mcp-metrics-service")
    OTEL_PROMETHEUS_ENABLED: bool = os.getenv("OTEL_PROMETHEUS_ENABLED", "true").lower() == "true"
    OTEL_PROMETHEUS_PORT: int = int(os.getenv("OTEL_PROMETHEUS_PORT", "9465"))
    OTEL_OTLP_ENDPOINT: str | None = os.getenv("OTEL_OTLP_ENDPOINT")

    # API Security
    METRICS_RATE_LIMIT: int = int(os.getenv("METRICS_RATE_LIMIT", "1000"))
    API_KEY_HASH_ALGORITHM: str = os.getenv("API_KEY_HASH_ALGORITHM", "sha256")

    # Performance
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))
    FLUSH_INTERVAL_SECONDS: int = int(os.getenv("FLUSH_INTERVAL_SECONDS", "30"))
    MAX_REQUEST_SIZE: str = os.getenv("MAX_REQUEST_SIZE", "10MB")


settings = Settings()
