from typing import Optional

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError
from app.logger import logger


class ExtractionService:
    """Main Orchestrator"""

    def __init__(self, client: HubSpotClient) -> None:
        self._client = client

    def start_scan(
        self,
        object_types: list[str],
        properties_by_object: dict[str, list[str]],
        last_modified_after_ms: Optional[int] = None,
    ) -> dict[str, dict]:
        """Starts a scan.

        Returns:
            The dictionary of extractions
        """
        extractions: dict[str, dict] = {}
        for object_type in object_types:
            try:
                record_count = 0
                for page in self._client.iter_objects(
                    object_type,
                    properties_by_object.get(object_type, []),
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
