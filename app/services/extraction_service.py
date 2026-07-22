from typing import Optional

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError
from app.logger import logger
from app.services.normalization_service import NormalizationService


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
        client: HubSpotClient,
    ) -> None:
        """Initializes the extraction service.

        Args:
            normalizer: Converts extracted records into storable output
                formats (JSON/Parquet). Not yet used by `start_scan` — held
                here in preparation for wiring in once a storage destination
                (e.g. MinIO) exists to write normalized output to.
            client: HubSpot client used to fetch records for each object
                type requested by a scan.
        """
        self._normalizer = normalizer
        self._client = client

    def start_scan(
        self,
        object_types: list[str],
        properties_by_object: dict[str, list[str]],
        associations_by_object: dict[str, list[str]],
        last_modified_after_ms: Optional[int] = None,
    ) -> dict[str, dict]:
        """Runs an extraction scan across one or more HubSpot object types.

        Fetches every page of records for each object type in turn via
        `HubSpotClient.iter_objects`, counting records as they arrive.
        Each object type is handled independently — a failure on one type
        (e.g. an unsupported object type, or a HubSpot API error) is
        recorded as a per-type failure and does not stop the remaining
        types from being scanned. Records themselves are not retained;
        only counts and status are reported.

        Args:
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

        Returns:
            A dict keyed by object type, where each value is either
            `{"status": "completed", "record_count": <int>}` or
            `{"status": "failed", "error": <str>}`.
        """
        extractions: dict[str, dict] = {}
        for object_type in object_types:
            try:
                record_count = 0
                for page in self._client.iter_objects(
                    object_type,
                    properties_by_object.get(object_type, []),
                    associations=associations_by_object.get(object_type, []),
                    last_modified_after_ms=last_modified_after_ms,
                ):
                    record_count += len(page)
                    extractions[object_type] = {
                        "status": "completed",
                        "record_count": record_count,
                    }
            except HubSpotClientError as e:
                logger.warning(f"Failed to scan {object_type}: {e}")
                extractions[object_type] = {"status": "failed", "error": str(e)}
            except Exception as e:
                logger.error(f"Failed to scan {object_type}: {e}")
                extractions[object_type] = {"status": "failed", "error": str(e)}
        return extractions
