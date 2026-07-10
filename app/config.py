
import logging
import sys

from pydantic import ValidationError, field_validator
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MINIMUM_KEY_LENGTH = 32
PLACEHOLDER_PREFIX = "REPLACE_WITH"

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Settings for HubSpot Service.
    """

    model_config = SettingsConfigDict(
        extra="forbid",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_VERSION: str
    APP_TITLE: str
    FLASK_ENV: str
    FLASK_DEBUG: bool
    SECRET_KEY: SecretStr
    PORT: int
    HOST: str
    ENVIRONMENT: str

    # Logging
    LOG_LEVEL: str
    LOG_FORMAT: str
    LOKI_ENABLED: bool

    # Database
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_SCHEMA: str

    # HubSpot
    HUBSPOT_ACCESS_TOKEN: SecretStr
    HUBSPOT_PORTAL_ID: str
    HUBSPOT_BASE_URL: str
    HUBSPOT_API_VERSION: str
    HUBSPOT_PAGE_SIZE: int
    HUBSPOT_RATE_LIMIT_RPS: int
    HUBSPOT_INCLUDE_ASSOCIATIONS: bool

    # Scans
    MAX_CONCURRENT_SCANS: int
    SCAN_TIMEOUT_HOURS: int
    CLEANUP_DAYS: int

    # HMAC
    HMAC_ENABLED: bool
    HMAC_SECRET_KEY_CORE: SecretStr
    HMAC_SECRET_KEY_ENGINEER: SecretStr
    HMAC_SIGNATURE_MAX_AGE: int

    # Minio
    MINIO_ENABLED: bool
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: SecretStr
    MINIO_SECRET_KEY: SecretStr
    MINIO_SECURE:bool
    MINIO_BUCKET: str

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP_ID: str
    KAFKA_AUTO_OFFSET_RESET: str
    KAFKA_ENABLE_AUTO_COMMIT: bool

    # Clickhouse
    CLICKHOUSE_ENABLED: bool
    CLICKHOUSE_HOST: str
    CLICKHOUSE_PORT: int
    CLICKHOUSE_USER: str
    CLICKHOUSE_PASSWORD: SecretStr
    CLICKHOUSE_DATABASE: str

    # PII
    PII_MASKING_ENABLED: bool
    PII_SERVICE_URL: str
    PII_HMAC_KEY: SecretStr
    PII_SERVICE_ID: str

    # CORS
    ALLOWED_ORIGINS: str

    # Integration
    BD_CORE_URL: str

    # =========================================================================================
    #                                      Field Validators
    # =========================================================================================

    @field_validator(
        "APP_VERSION", "APP_TITLE", "FLASK_ENV", "HOST", "ENVIRONMENT",
        "LOG_LEVEL", "LOG_FORMAT",
        "DB_HOST", "DB_NAME", "DB_USER", "DB_SCHEMA",
        "HUBSPOT_PORTAL_ID", "HUBSPOT_BASE_URL", "HUBSPOT_API_VERSION",
        "MINIO_ENDPOINT", "MINIO_BUCKET",
        "KAFKA_BOOTSTRAP_SERVERS", "KAFKA_CONSUMER_GROUP_ID", "KAFKA_AUTO_OFFSET_RESET",
        "CLICKHOUSE_HOST", "CLICKHOUSE_USER", "CLICKHOUSE_DATABASE",
        "PII_SERVICE_URL", "PII_SERVICE_ID",
        "ALLOWED_ORIGINS", "BD_CORE_URL",
    )
    @classmethod
    def ensure_non_empty_str(cls, v: str) -> str:
        trimmed = v.strip()

        if trimmed == "":
            raise ValueError("Must be non-empty")

        return trimmed

    @field_validator(
        "DB_PASSWORD", "HUBSPOT_ACCESS_TOKEN",
        "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
        "CLICKHOUSE_PASSWORD", "PII_HMAC_KEY",
    )
    @classmethod
    def ensure_non_empty_secret(cls, v: SecretStr) -> SecretStr:
        trimmed = v.get_secret_value().strip()

        if trimmed == "":
            raise ValueError("Must be non-empty")

        if trimmed.startswith(PLACEHOLDER_PREFIX):
            raise ValueError("Must not be a placeholder")

        return v

    @field_validator("SECRET_KEY", "HMAC_SECRET_KEY_CORE", "HMAC_SECRET_KEY_ENGINEER")
    @classmethod
    def ensure_non_empty_and_minimum_length_secret(cls, v: SecretStr) -> SecretStr:
        trimmed = v.get_secret_value().strip()

        if trimmed == "":
            raise ValueError("Must be non-empty")

        if trimmed.startswith(PLACEHOLDER_PREFIX):
            raise ValueError("Must not be a placeholder")

        if len(trimmed) < MINIMUM_KEY_LENGTH:
            raise ValueError(f"Must have a minimum of {MINIMUM_KEY_LENGTH} characters")

        return v

def validate_settings() -> Settings:
    try:
        return Settings()   # pyright: ignore[reportCallIssue]
    except ValidationError as ve:
        errors = ve.errors()

        for e in errors:
            print(e)

        sys.exit(1)
