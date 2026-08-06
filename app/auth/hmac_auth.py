import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps

from flask import current_app, request

from app.config import Settings


def require_hmac(requires_engineer_key: bool = False):
    """
    Require HMAC authentication for a Flask endpoint.

    When HMAC authentication is enabled, this decorator validates:
    1. The presence of the ``X-Timestamp`` and ``X-Signature`` headers.
    2. That the request timestamp is within the configured maximum age.
    3. That the supplied HMAC signature matches the expected signature.

    The signature is computed using SHA-256 over the following payload:
    ```
    <HTTP_METHOD>
    <REQUEST_PATH>
    <TIMESTAMP>
    <RAW_REQUEST_BODY>
    ```

    The secret key is selected based on ``requires_engineer_key``:
        - False: ``HMAC_SECRET_KEY_CORE``
        - True: ``HMAC_SECRET_KEY_ENGINEER``

    If ``HMAC_ENABLED`` is False, authentication is skipped and the wrapped
    endpoint is executed immediately.

    Args:
        requires_engineer_key:
            Whether to use the engineer HMAC secret instead of the core secret.

    Returns:
        A Flask view decorator that returns HTTP 401 when authentication fails.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            settings: Settings = current_app.extensions["settings"]
            if not settings.HMAC_ENABLED:
                return fn(*args, **kwargs)

            timestamp = request.headers.get("X-Timestamp")
            signature = request.headers.get("X-Signature")
            if not (timestamp and signature):
                return {
                    "code": "INVALID_HEADERS",
                    "error": "Invalid/missing HMAC headers",
                }, 401

            try:
                request_time = datetime.fromtimestamp(int(timestamp), tz=UTC)
            except (ValueError, OverflowError, OSError):
                return {
                    "code": "INVALID_HEADERS",
                    "error": "Invalid timestamp",
                }, 401

            now = datetime.now(UTC)
            if (
                abs((now - request_time).total_seconds())
                > settings.HMAC_SIGNATURE_MAX_AGE
            ):
                return {
                    "code": "AUTH_ERR",
                    "error": "Invalid timestamp",
                }, 401

            key = (
                settings.HMAC_SECRET_KEY_ENGINEER
                if requires_engineer_key
                else settings.HMAC_SECRET_KEY_CORE
            )
            # full_path includes the query string (with a trailing "?" even
            # when there's no query string, hence the rstrip).
            signed_path = request.full_path.rstrip("?")
            expected = hmac.new(
                key=key.get_secret_value().encode(),
                msg=f"{request.method}\n{signed_path}\n{timestamp}\n{request.get_data(as_text=True)}".encode(),
                digestmod=hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected):
                return {
                    "code": "AUTH_ERR",
                    "error": "Invalid signature",
                }, 401

            return fn(*args, **kwargs)

        return wrapper

    return decorator
