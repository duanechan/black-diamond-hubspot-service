from typing import Optional

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError
from app.logger import logger
from app.services.normalization_service import NormalizationService
from app.storage.minio_client import MinioClient, MinioClientError


class ExtractionService:
    """Orchestrates HubSpot data extraction scans.

    Coordinates fetching records for one or more HubSpot object types via
    `HubSpotClient`, reporting per-object-type results. Runs synchronously —
    a scan blocks until every requested object type has been fully fetched
    (or has failed) before returning. Does not persist scan state; results
    exist only for the duration of the call.
    """

    def __init__(
        self,
        normalizer: NormalizationService,
        minio: MinioClient,
        client: HubSpotClient,
    ) -> None:
        """Initializes the extraction service.

        Args:
            normalizer: Converts extracted records into storable output
                formats (JSON/Parquet) before upload.
            minio: Storage client used to upload normalized pages when a
                scan requests an `output_format`. A no-op if constructed
                with `enabled=False`.
            client: HubSpot client used to fetch records for each object
                type requested by a scan.
        """
        self._normalizer = normalizer
        self._minio = minio
        self._client = client

    def start_scan(
        self,
        scan_id: str,
        org_id: str,
        object_types: list[str],
        properties_by_object: dict[str, list[str]],
        associations_by_object: dict[str, list[str]],
        last_modified_after_ms: Optional[int] = None,
        output_format: Optional[str] = None,
        destination: Optional[dict] = None,
    ) -> dict[str, dict]:
        """Runs an extraction scan across one or more HubSpot object types.

        Fetches every page of records for each object type in turn via
        `HubSpotClient.iter_objects`, counting records as they arrive. If
        `output_format` is set, each page is also normalized and uploaded
        to MinIO before moving to the next page.

        Each object type is handled independently — a failure on one type
        (whether fetching, normalizing, or uploading) is recorded as a
        per-type failure and does not stop the remaining types from being
        scanned. A failure partway through a type discards that type's
        partial progress; it is reported as failed, not partially
        completed.

        Args:
            scan_id: Identifier for this scan, used to namespace uploaded
                objects in MinIO. Not otherwise used.
            org_id: Organization identifier, used to namespace uploaded
                objects in MinIO. Not otherwise used.
            object_types: HubSpot object types to scan (e.g. "contacts",
                "companies"). Unrecognized types are attempted like any
                other and will simply fail with a HubSpot API error.
            properties_by_object: Property names to request per object
                type. An object type missing from this dict is fetched
                with no explicit properties (HubSpot's default minimal
                set).
            associations_by_object: Associated object types to request
                per object type (e.g. {"contacts": ["companies"]}). An
                object type missing from this dict is fetched with no
                associations.
            last_modified_after_ms: If set, restricts every object type
                in this scan to records modified at or after this Unix
                timestamp in milliseconds (an incremental scan via
                HubSpot's Search API). If omitted, every object type is
                fully scanned.
            output_format: If set ("json" or "parquet"), each fetched
                page is normalized to this format and uploaded to MinIO.
                If omitted, records are only counted, never stored.
            destination: Controls where extracted data should be sent. Supported
                keys are:

                - "minio_bucket": enables MinIO upload.
                - "kafka_publish": publishes extraction events to Kafka.
                - "clickhouse_load": loads normalized data into ClickHouse.

                Unsupported destinations are currently ignored.

        Returns:
            A dict keyed by object type, where each value is either
            `{"status": "completed", "record_count": <int>, "uploaded_keys": [...]}`
            (the `uploaded_keys` list is empty if `output_format` was not
            set) or `{"status": "failed", "error": <str>}`.
        """
        destination = destination or {}

        upload_to_minio = "minio_bucket" in destination
        publish_to_kafka = destination.get("kafka_publish", False)
        load_to_clickhouse = destination.get("clickhouse_load", False)

        if publish_to_kafka:
            # TODO: Publish extraction event to Kafka.
            pass

        if load_to_clickhouse:
            # TODO: Load normalized data into ClickHouse.
            pass

        normalizers = {
            "json": self._normalizer.to_json,
            "parquet": self._normalizer.to_parquet,
        }

        if output_format is not None and output_format not in normalizers:
            raise ValueError(
                f"Unsupported output_format: {output_format!r}. Must be one of: {list(normalizers)}"
            )

        extractions: dict[str, dict] = {}
        for object_type in object_types:
            try:
                record_count = 0
                uploaded_keys: list[str] = []
                for page_num, page in enumerate(
                    self._client.iter_objects(
                        object_type,
                        properties_by_object.get(object_type, []),
                        associations=associations_by_object.get(object_type, []),
                        last_modified_after_ms=last_modified_after_ms,
                    ),
                    start=1,
                ):
                    record_count += len(page)

                    if output_format is not None and upload_to_minio:
                        normalize = normalizers[output_format]
                        data = normalize(page)
                        key = self._minio.upload(
                            data=data,
                            org_id=org_id,
                            scan_id=scan_id,
                            object_type=object_type,
                            page=page_num,
                            output_format=output_format,
                        )
                        if key is not None:
                            uploaded_keys.append(key)

                    extractions[object_type] = {
                        "status": "completed",
                        "record_count": record_count,
                        "uploaded_keys": uploaded_keys,
                    }
            except HubSpotClientError as e:
                logger.warning(f"Failed to scan {object_type}: {e}")
                extractions[object_type] = {"status": "failed", "error": str(e)}
            except MinioClientError as e:
                logger.warning(f"Failed to upload {object_type} data: {e}")
                extractions[object_type] = {"status": "failed", "error": str(e)}
            except Exception as e:
                logger.error(f"Failed to scan {object_type}: {e}")
                extractions[object_type] = {"status": "failed", "error": str(e)}
        return extractions
