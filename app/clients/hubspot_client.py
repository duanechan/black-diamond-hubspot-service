from typing import Iterator, Optional, cast

from hubspot import HubSpot
from hubspot.crm.objects import (
    ApiException,
    CollectionResponseSimplePublicObjectWithAssociationsForwardPaging,
)

from app.auth.hubspot_auth import HubSpotAuth
from app.logger import logger


class HubSpotClientError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class HubSpotClient:
    """Client for HubSpot API"""

    def __init__(
        self,
        auth: HubSpotAuth,
        page_size: int = 100,
        rate_limit: int = 10,
        include_associations: bool = True,
        timeout: int = 30,
    ) -> None:
        self._client = HubSpot(access_token=auth.access_token)
        self._auth = auth
        self._page_size = page_size
        self._rate_limit = rate_limit
        self._include_associations = include_associations
        self._timeout = timeout

    def iter_objects(
        self,
        object_type: str,
        properties: list[str],
        last_modified_after_ms: Optional[int] = None,
    ) -> Iterator[list[dict]]:
        if last_modified_after_ms is not None:
            raise NotImplementedError("'last_modified_after_ms' not yet implemented")

        after: Optional[str] = None
        try:
            while True:
                page = cast(
                    CollectionResponseSimplePublicObjectWithAssociationsForwardPaging,
                    self._client.crm.objects.basic_api.get_page(
                        object_type=object_type,
                        properties=properties,
                        limit=self._page_size,
                        after=after,
                    ),
                )

                results = [record.to_dict() for record in (page.results or [])]
                if len(results) > 0:
                    yield results
                if page.paging is None or page.paging.next is None:
                    break
                else:
                    after = page.paging.next.after
        except ApiException as e:
            logger.error(f"Failed to retrieve paginated-list of {object_type}: {e}")
            raise HubSpotClientError(
                f"Failed to retrieve paginated-list of {object_type}: {e}"
            )

    def ping(self) -> bool:
        if self._auth.is_authenticated(max_age_seconds=300):
            return True

        try:
            return self._auth.validate()
        except Exception as e:
            logger.warning(f"HubSpot ping failed: {e}")
            return False
