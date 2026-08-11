import json
import threading
from datetime import UTC, datetime

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError
from app.constants import KAFKA_TOPIC_PREFIX_BY_OBJECT
from app.logger import logger
from app.repositories.scan_repository import ScanRepository
from app.services.normalization_service import NormalizationService
from app.services.pii_service import PIIService
from app.storage.clickhouse_client import ClickHouseClient, ClickHouseClientError
from app.storage.kafka_producer import KafkaProducer
from app.storage.minio_client import MinioClient, MinioClientError


class ExtractionService:
    """Orchestrates HubSpot data extraction scans.

    Coordinates fetching records for one or more HubSpot object types via
    `HubSpotClient`, persisting per-object-type progress to `ScanRepository`
    as it goes. Designed to be run in a background thread - `start_scan_async`
    does not return a result; callers poll persisted scan state instead
    (e.g. via `GET /api/scan/{id}/status`). Supports cooperative
    cancellation via `cancel_scan`.
    """

    def __init__(
        self,
        normalizer: NormalizationService,
        minio: MinioClient,
        kafka: KafkaProducer,
        pii: PIIService,
        clickhouse: ClickHouseClient,
        client: HubSpotClient,
        scans: ScanRepository,
        environment: str,
    ) -> None:
        """Initializes the extraction service.

        Args:
            normalizer: Converts extracted records into storable output
                formats (JSON/Parquet) before upload.
            minio: Storage client used to upload normalized pages when a
                scan requests an `output_format`. A no-op if constructed
                with `enabled=False`.
            kafka: Publishes one message per record to Kafka when a scan
                requests `destination.kafka_publish`.
            pii: Masks PII fields in records before they're published to
                Kafka. A no-op if constructed with `enabled=False`.
            client: HubSpot client used to fetch records for each object
                type requested by a scan.
            scans: Repository used to persist scan/progress state.
            environment: Deployment environment (e.g. "dev", "stage",
                "prod"), used to select the correct Kafka topic per
                object type (e.g. "hs.contacts.dev").
        """
        self._normalizer = normalizer
        self._minio = minio
        self._kafka = kafka
        self._pii = pii
        self._clickhouse = clickhouse
        self._client = client
        self._scans = scans
        self._environment = environment
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_events_lock = threading.Lock()

    def validate_scan_params(
        self,
        output_format: str | None,
        destination: dict | None,
    ) -> None:
        """Validates scan parameters that must fail synchronously.

        Args:
            output_format: The requested output format, if any.
            destination: The requested destination config, if any.

        Raises:
            ValueError: If `output_format` is set but unsupported.
        """
        valid_formats = {"json", "parquet"}
        if output_format is not None and output_format not in valid_formats:
            raise ValueError(
                f"Unsupported output_format: {output_format!r}. Must be one of: {sorted(valid_formats)}"
            )

    def start_scan_async(
        self,
        scan_id: str,
        org_id: str,
        object_types: list[str],
        properties_by_object: dict[str, list[str]],
        associations_by_object: dict[str, list[str]],
        last_modified_after_ms: int | None = None,
        output_format: str | None = None,
        destination: dict | None = None,
    ) -> threading.Thread:
        """Starts a scan in a background thread and returns immediately.

        Registers a cancel event for this scan before starting the
        thread, so `cancel_scan` can be called safely even if it races
        with the thread's own startup.

        Args:
            scan_id: Identifier for this scan. Must already exist as a
                persisted scan (via `ScanRepository.create`).
            org_id: Organization identifier.
            object_types: HubSpot object types to scan.
            properties_by_object: Property names to request per object type.
            associations_by_object: Associated object types to request
                per object type.
            last_modified_after_ms: If set, restricts every object type
                to records modified at or after this timestamp.
            output_format: If set, each fetched page is normalized and
                uploaded to MinIO.
            destination: Controls where extracted data is sent.

        Returns:
            The started (daemon) thread.
        """
        with self._cancel_events_lock:
            self._cancel_events[scan_id] = threading.Event()

        thread = threading.Thread(
            target=self._run_scan,
            kwargs={
                "scan_id": scan_id,
                "org_id": org_id,
                "object_types": object_types,
                "properties_by_object": properties_by_object,
                "associations_by_object": associations_by_object,
                "last_modified_after_ms": last_modified_after_ms,
                "output_format": output_format,
                "destination": destination,
            },
            daemon=True,
        )
        thread.start()
        return thread

    def cancel_scan(self, scan_id: str) -> bool:
        """Requests cancellation of an in-progress scan.

        This is cooperative, not immediate - the running thread notices
        the request the next time it checks between object types (or,
        for the object type currently mid-fetch, after its current page
        finishes). Object types already complete are unaffected; object
        types not yet started are marked "cancelled" rather than fetched.

        Args:
            scan_id: The scan to cancel.

        Returns:
            True if a cancel signal was sent (the scan was found and
            still tracked as running); False if no running scan with
            that ID was found (e.g. it already finished, or never
            existed).
        """
        with self._cancel_events_lock:
            event = self._cancel_events.get(scan_id)
        if event is None:
            return False
        event.set()
        return True

    def _run_scan(
        self,
        scan_id: str,
        org_id: str,
        object_types: list[str],
        properties_by_object: dict[str, list[str]],
        associations_by_object: dict[str, list[str]],
        last_modified_after_ms: int | None,
        output_format: str | None,
        destination: dict | None,
    ) -> None:
        """Runs an extraction scan, persisting progress as it goes.

        Checks the scan's cancel event before starting each object type;
        if set, remaining (not-yet-started) object types are marked
        "cancelled" instead of being fetched. Cleans up the cancel event
        when the scan finishes, regardless of outcome.
        """
        destination = destination or {}
        load_to_clickhouse = destination.get("clickhouse_load", False)
        upload_to_minio = "minio_bucket" in destination
        publish_to_kafka = destination.get("kafka_publish", False)

        normalizers = {
            "json": self._normalizer.to_json,
            "parquet": self._normalizer.to_parquet,
        }

        with self._cancel_events_lock:
            cancel_event = self._cancel_events.get(scan_id, threading.Event())

        self._scans.update_status(scan_id, "in_progress")

        try:
            for object_type in object_types:
                if cancel_event.is_set():
                    self._scans.update_object_progress(
                        scan_id, object_type, {"status": "cancelled"}
                    )
                    continue

                try:
                    record_count = 0
                    uploaded_keys: list[str] = []
                    page_num = 0
                    for page_num, (_next_after, page) in enumerate(
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

                        if publish_to_kafka:
                            self._publish_page(
                                object_type, org_id, scan_id, page_num, page
                            )

                        if load_to_clickhouse:
                            self._clickhouse.insert_records(object_type, page)

                        if cancel_event.is_set():
                            # Stop mid-object-type too - don't finish
                            # fetching remaining pages once cancelled.
                            break

                    if output_format is not None and upload_to_minio and page_num > 0:
                        metadata_key = self._upload_metadata(
                            org_id=org_id,
                            scan_id=scan_id,
                            object_type=object_type,
                            total_records=record_count,
                            pages=page_num,
                            last_modified_after_ms=last_modified_after_ms,
                        )
                        if metadata_key is not None:
                            uploaded_keys.append(metadata_key)

                    status = "cancelled" if cancel_event.is_set() else "complete"
                    self._scans.update_object_progress(
                        scan_id,
                        object_type,
                        {
                            "status": status,
                            "records_extracted": record_count,
                            "pages_downloaded": page_num,
                            "associations_fetched": bool(
                                associations_by_object.get(object_type)
                            ),
                            "minio_path": (
                                f"s3://{destination.get('minio_bucket')}/{org_id}/{scan_id}/{object_type}/"
                                if upload_to_minio
                                else None
                            ),
                        },
                    )
                except HubSpotClientError as e:
                    logger.warning(f"Failed to scan {object_type}: {e}")
                    self._scans.update_object_progress(
                        scan_id, object_type, {"status": "failed", "error": str(e)}
                    )
                except MinioClientError as e:
                    logger.warning(f"Failed to upload {object_type} data: {e}")
                    self._scans.update_object_progress(
                        scan_id, object_type, {"status": "failed", "error": str(e)}
                    )
                except ClickHouseClientError as e:
                    logger.warning(
                        f"Failed to load {object_type} data into ClickHouse: {e}"
                    )
                    self._scans.update_object_progress(
                        scan_id, object_type, {"status": "failed", "error": str(e)}
                    )
                except KeyError as e:
                    logger.warning(f"No Kafka topic configured for {object_type}: {e}")
                    self._scans.update_object_progress(
                        scan_id,
                        object_type,
                        {
                            "status": "failed",
                            "error": f"No Kafka topic configured for object type {object_type!r}",
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to scan {object_type}: {e}")
                    self._scans.update_object_progress(
                        scan_id, object_type, {"status": "failed", "error": str(e)}
                    )

            final_scan = self._scans.get(scan_id)
            statuses = {entry.get("status") for entry in final_scan.progress.values()}
            if cancel_event.is_set():
                final_status = "cancelled"
            elif "failed" in statuses:
                final_status = "failed"
            else:
                final_status = "completed"
            self._scans.update_status(scan_id, final_status)
        finally:
            with self._cancel_events_lock:
                self._cancel_events.pop(scan_id, None)

    def _publish_page(
        self,
        object_type: str,
        org_id: str,
        scan_id: str,
        page_num: int,
        page: list[dict],
    ) -> None:
        """Publishes one Kafka message per record in a page, then flushes."""
        topic = f"{KAFKA_TOPIC_PREFIX_BY_OBJECT[object_type]}.{self._environment}"
        extracted_at = datetime.now(UTC).isoformat()

        page = self._pii.mask(page)

        for record in page:
            message = {
                "meta": {
                    "source": "hubspot",
                    "object": object_type,
                    "org_id": org_id,
                    "scan_id": scan_id,
                    "page": page_num,
                    "extracted_at": extracted_at,
                },
                "record": {
                    "hs_object_id": record.get("id"),
                    **record.get("properties", {}),
                    "associations": record.get("associations"),
                },
            }
            self._kafka.produce(
                topic,
                value=json.dumps(message, default=str).encode("utf-8"),
                key=scan_id,
            )

        self._kafka.flush()

    def _upload_metadata(
        self,
        org_id: str,
        scan_id: str,
        object_type: str,
        total_records: int,
        pages: int,
        last_modified_after_ms: int | None,
    ) -> str | None:
        """Uploads a summary metadata file for a completed object type."""
        metadata = {
            "object": object_type,
            "scan_id": scan_id,
            "total_records": total_records,
            "pages": pages,
            "filter": (
                {"last_modified_after_ms": last_modified_after_ms}
                if last_modified_after_ms is not None
                else None
            ),
            "created_at": datetime.now(UTC).isoformat(),
        }
        return self._minio.upload_metadata(
            org_id=org_id,
            scan_id=scan_id,
            object_type=object_type,
            data=json.dumps(metadata).encode("utf-8"),
        )
