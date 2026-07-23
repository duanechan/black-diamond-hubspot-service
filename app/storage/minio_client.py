from io import BytesIO
from typing import Optional

from minio import Minio

from app.logger import logger


class MinioClientError(ValueError):
    """Raised when a MinIO operation fails."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class MinioClient:
    """Client for uploading normalized extraction output to MinIO.

    Entirely inert when constructed with `enabled=False` — no connection
    is attempted, and every method becomes a no-op, so the rest of the
    service can hold a `MinioClient` unconditionally without needing to
    check `MINIO_ENABLED` itself.
    """

    def __init__(
        self,
        enabled: bool,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
        bucket: str,
    ) -> None:
        """Initializes the MinIO client.

        When `enabled` is True, connects immediately and verifies the
        target bucket exists — this is a real network call, made eagerly
        so a missing bucket or bad connection fails at startup rather
        than on the first upload attempt.

        Args:
            enabled: Whether MinIO is enabled. When False, no connection
                is made and every method becomes a no-op.
            endpoint: MinIO server endpoint (host:port).
            access_key: MinIO access key.
            secret_key: MinIO secret key.
            secure: Whether to use HTTPS for the connection.
            bucket: Name of the bucket to upload objects to. Must already
                exist; this client does not create buckets.

        Raises:
            MinioClientError: If `enabled` is True and the bucket does
                not exist.
        """
        self._enabled = enabled
        self._bucket = bucket

        if not self._enabled:
            self._client = None
            return

        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if not self._client.bucket_exists(bucket):
            raise MinioClientError(f"MinIO bucket '{bucket}' does not exist")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def ping(self) -> bool:
        """Checks whether MinIO is reachable.

        Always returns False when the client is disabled, without
        attempting any connection. Never raises — failures are logged
        and reported as False, matching `HubSpotClient.ping()`.

        Returns:
            True if MinIO is reachable; False otherwise.
        """
        if not self.enabled:
            return False
        assert self._client is not None
        try:
            self._client.list_buckets()
            return True
        except Exception as e:
            logger.warning(f"MinIO ping failed: {e}")
            return False

    def upload(
        self,
        data: bytes,
        org_id: str,
        scan_id: str,
        object_type: str,
        page: int,
        output_format: str,
    ) -> Optional[str]:
        """Uploads normalized data to MinIO.

        Args:
            data: The normalized bytes to upload (JSON or Parquet).
            org_id: Organization identifier, used to namespace the object key.
            scan_id: Scan identifier, used to namespace the object key.
            object_type: HubSpot object type this data belongs to.
            page: Page number, to keep multiple pages of the same object
                type from overwriting each other.
            output_format: File extension to use for the object key
                ("json" or "parquet").

        Returns:
            The object key the data was uploaded to, or None if MinIO is
            disabled.

        Raises:
            MinioClientError: If the upload fails.
        """
        if not self.enabled:
            return None
        assert self._client is not None

        object_key = f"{org_id}/{scan_id}/{object_type}/page_{page}.{output_format}"

        try:
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=object_key,
                data=BytesIO(data),
                length=len(data),
            )
        except Exception as e:
            raise MinioClientError(f"Failed to upload to '{object_key}': {e}")

        return object_key
