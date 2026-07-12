import sys
from typing import Any

from pydantic import ValidationError, field_validator
from pydantic.types import SecretStr
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import constants
from app.logger import is_json_logging, logger


class VariableError(ValueError):
    """Fallback error"""


class EmptyVariableError(ValueError):
    """Raised when variable is empty."""

    def __init__(self):
        super().__init__("Value cannot be empty")


class PlaceholderVariableError(ValueError):
    """Raised when variable is a placeholder."""

    def __init__(self):
        super().__init__("Placeholder value detected")


class MinimumLengthNotMetError(ValueError):
    """Raised when variable length does not meet a minimum length."""

    def __init__(self):
        super().__init__(
            f"value must be at least {constants.MINIMUM_KEY_LENGTH} characters"
        )


class InvalidLogLevelError(ValueError):
    """Raised when log level is invalid."""

    def __init__(self):
        super().__init__("Invalid log level")


ERROR_REGISTRY = {
    VariableError: (
        "VariableError",
        "Refer to the technical documentation for guidance.",
    ),
    EmptyVariableError: (
        "EmptyVariableError",
        "Set the variable to a non-empty value.",
    ),
    PlaceholderVariableError: (
        "PlaceholderVariableError",
        "Replace the placeholder value with a real secret.",
    ),
    MinimumLengthNotMetError: (
        "MinimumLengthNotMetError",
        f"Use a value at least {constants.MINIMUM_KEY_LENGTH} characters long.",
    ),
    InvalidLogLevelError: (
        "InvalidLogLevelError",
        f"Use one of: {', '.join(constants.LOG_LEVELS)}",
    ),
}


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
    MINIO_SECURE: bool
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
        "APP_VERSION",
        "APP_TITLE",
        "FLASK_ENV",
        "HOST",
        "ENVIRONMENT",
        "LOG_FORMAT",
        "DB_HOST",
        "DB_NAME",
        "DB_USER",
        "DB_SCHEMA",
        "HUBSPOT_PORTAL_ID",
        "HUBSPOT_BASE_URL",
        "HUBSPOT_API_VERSION",
        "MINIO_ENDPOINT",
        "MINIO_BUCKET",
        "KAFKA_BOOTSTRAP_SERVERS",
        "KAFKA_CONSUMER_GROUP_ID",
        "KAFKA_AUTO_OFFSET_RESET",
        "CLICKHOUSE_HOST",
        "CLICKHOUSE_USER",
        "CLICKHOUSE_DATABASE",
        "PII_SERVICE_URL",
        "PII_SERVICE_ID",
        "ALLOWED_ORIGINS",
        "BD_CORE_URL",
    )
    @classmethod
    def ensure_non_empty_str(cls, v: str) -> str:
        trimmed = v.strip()

        if trimmed == "":
            raise EmptyVariableError

        return trimmed

    @field_validator(
        "DB_PASSWORD",
        "HUBSPOT_ACCESS_TOKEN",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "CLICKHOUSE_PASSWORD",
        "PII_HMAC_KEY",
    )
    @classmethod
    def ensure_non_empty_secret(cls, v: SecretStr) -> SecretStr:
        trimmed = v.get_secret_value().strip()

        if trimmed == "":
            raise EmptyVariableError

        if trimmed.startswith(constants.PLACEHOLDER_PREFIX):
            raise PlaceholderVariableError

        return v

    @field_validator("SECRET_KEY", "HMAC_SECRET_KEY_CORE", "HMAC_SECRET_KEY_ENGINEER")
    @classmethod
    def ensure_non_empty_and_minimum_length_secret(cls, v: SecretStr) -> SecretStr:
        trimmed = v.get_secret_value().strip()

        if trimmed == "":
            raise EmptyVariableError

        if trimmed.startswith(constants.PLACEHOLDER_PREFIX):
            raise PlaceholderVariableError

        if len(trimmed) < constants.MINIMUM_KEY_LENGTH:
            raise MinimumLengthNotMetError

        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def ensure_valid_log_level(cls, level: str) -> str:
        if level.lower() not in constants.LOG_LEVELS:
            raise InvalidLogLevelError

        return level


def format_text(error_details: dict[type[ValueError], list[ErrorDetails]]) -> list[str]:
    text_msg: list[str] = []

    for error_type, details in error_details.items():
        title, fix = ERROR_REGISTRY[error_type]
        text_msg.append("-" * 80)
        text_msg.append(f" Error: {title} ({len(details)})")
        text_msg.append(f" Fix: {fix}")
        text_msg.extend([f"  * {e['loc'][0]}" for e in details])
        text_msg.append("-" * 80)
        text_msg.append("")

    return text_msg


def format_json(
    error_details: dict[type[ValueError], list[ErrorDetails]],
) -> list[dict[str, Any]]:
    json_msg: list[dict[str, Any]] = []

    for error_type, details in error_details.items():
        title, fix = ERROR_REGISTRY[error_type]
        json_msg.append(
            {"type": title, "fix": fix, "fields": [e["loc"][0] for e in details]}
        )

    return json_msg


def build_errors(
    details: list[ErrorDetails],
) -> dict[type[ValueError], list[ErrorDetails]]:
    errors: dict[type[ValueError], list[ErrorDetails]] = {}

    for e in details:
        error = e.get("ctx", {}).get("error")
        error_type = type(error)
        if error_type not in ERROR_REGISTRY:
            errors.setdefault(VariableError, []).append(e)
        else:
            errors.setdefault(error_type, []).append(e)  # pyright: ignore[reportArgumentType]

    return errors


def validate_settings() -> Settings:
    """Loads and validates the application settings.

    If validation fails, logs a detailed summary of the validation errors and
    terminates the process with exit code `1`.

    Returns:
        The validated application settings.
    """
    try:
        return Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as ve:
        errors = ve.errors()
        error_details = build_errors(errors)

        if is_json_logging():
            logger.error(
                f"{len(errors)} validation error(s) found",
                extra={"validation_errors": format_json(error_details)},
            )
        else:
            logger.error(
                "\n".join(
                    [
                        f"{len(errors)} Validation Error(s) found:",
                        "\n".join(format_text(error_details)),
                    ]
                )
            )

        sys.exit(1)
