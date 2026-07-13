import time
from typing import Iterator, Optional

import requests

from app.auth.hubspot_auth import HubSpotAuth
from app.logger import logger


class HubSpotClientError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class HubSpotClient:
    """Client for HubSpot API"""

    ALLOWED_OBJECTS = [
        "contacts",
        "companies",
        "deals",
        "tickets",
        "leads",
        "owners",
        "engagements",
        "associations",
    ]

    def __init__(
        self,
        auth: HubSpotAuth,
        page_size: int = 100,
        rate_limit: int = 10,
        include_associations: bool = True,
        timeout: int = 30,
    ) -> None:
        self._auth = auth
        self._page_size = page_size
        self._rate_limit = rate_limit
        self._include_associations = include_associations
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
    ) -> dict:
        MAX_ATTEMPTS = 5
        url = f"{self._auth.base_url}{path}"

        for _ in range(MAX_ATTEMPTS):
            response = requests.request(
                method=method,
                url=url,
                headers=self._auth.get_headers(),
                params=params,
                timeout=self._timeout,
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", self._rate_limit))
                logger.warning(f"Rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.json()

        raise HubSpotClientError(
            f"Failed {method} {path} after {MAX_ATTEMPTS} attempts"
        )

    def iter_objects(
        self,
        object_type: str,
        properties: list[str],
        last_modified_after_ms: Optional[int] = None,
    ) -> Iterator[list[dict]]:
        object_type = object_type.lower()
        if object_type not in self.ALLOWED_OBJECTS:
            raise HubSpotClientError(
                f"'{object_type}' object is unsupported or does not exist"
            )

        if last_modified_after_ms is not None:
            raise NotImplementedError("Incremental scanning is not yet supported")

        after: Optional[str] = None

        while True:
            params = {"limit": self._page_size, "properties": ",".join(properties)}
            if after:
                params["after"] = after

            data = self._request(
                method="GET",
                path=f"/crm/{self._auth.api_version}/objects/{object_type}",
                params=params,
            )
            results = data.get("results", [])
            if len(results) > 0:
                yield results

            next_cursor = data.get("paging", {}).get("next", {}).get("after")
            if next_cursor:
                after = next_cursor
            else:
                break

    def ping(self) -> bool:
        if self._auth.is_authenticated(max_age_seconds=300):
            return True

        try:
            return self._auth.validate()
        except Exception as e:
            logger.warning(f"HubSpot ping failed: {e}")
            return False
