from typing import Iterator, Optional, cast

from hubspot import HubSpot
from hubspot.crm.objects import (
    ApiException,
    CollectionResponseSimplePublicObjectWithAssociationsForwardPaging,
    CollectionResponseWithTotalSimplePublicObjectForwardPaging,
)
from hubspot.crm.objects.models import Filter, FilterGroup, PublicObjectSearchRequest
from urllib3.util.retry import Retry

from app.auth.hubspot_auth import HubSpotAuth
from app.logger import logger


class HubSpotClientError(Exception):
    """Raised when a HubSpot API request fails after all retries are exhausted."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class HubSpotClient:
    """Client for HubSpot API"""

    def __init__(
        self,
        auth: HubSpotAuth,
        page_size: int = 100,
        include_associations: bool = True,
        max_retries: int = 5,
    ) -> None:
        """Initializes the HubSpot client.

        Args:
            auth: Provides the access token used to authenticate requests.
            page_size: Number of records to request per page. HubSpot's
                list/search endpoints cap this at 100.
            include_associations: Master switch for association fetching. If
                False, associations are never requested regardless of what's
                passed to `iter_objects`. If True, per-call `associations`
                lists are respected.
            max_retries: Maximum number of retry attempts for failed
                requests (429/500/502/503/504), handled by the underlying
                SDK's transport layer.
        """
        self._client = HubSpot(
            access_token=auth.access_token,
            retry=Retry(
                total=max_retries,
                status_forcelist=[429, 500, 502, 503, 504],
            ),
        )
        self._auth = auth
        self._page_size = page_size
        self._include_associations = include_associations

    def iter_objects(
        self,
        object_type: str,
        properties: list[str],
        associations: Optional[list[str]] = None,
        last_modified_after_ms: Optional[int] = None,
    ) -> Iterator[list[dict]]:
        """Iterates over pages of HubSpot CRM records for a given object type.

        Uses the standard list endpoint for a full scan, or the Search API
        (filtered on `lastmodifieddate`) when `last_modified_after_ms` is
        given, for incremental scans. Follows cursor-based pagination
        automatically, yielding one page (list of records) at a time.

        Args:
            object_type: HubSpot object type to fetch (e.g. "contacts").
            properties: Property names to include on each returned record.
            associations: Object types to fetch associated record IDs for
                (e.g. ["companies"]). Ignored entirely if the client was
                constructed with `include_associations=False`.
            last_modified_after_ms: If set, only returns records modified
                at or after this Unix timestamp in milliseconds, using the
                Search API instead of the list endpoint.

        Yields:
            Each page's records, as plain dicts (converted from the SDK's
            typed response objects). Empty pages are never yielded.

        Raises:
            HubSpotClientError: If a request fails (wraps the underlying
                ApiException).
        """
        after: Optional[str] = None
        try:
            while True:
                if last_modified_after_ms is None:
                    page = cast(
                        CollectionResponseSimplePublicObjectWithAssociationsForwardPaging,
                        self._client.crm.objects.basic_api.get_page(
                            object_type=object_type,
                            associations=(associations or [])
                            if self._include_associations
                            else [],
                            properties=properties,
                            limit=self._page_size,
                            after=after,
                        ),
                    )
                else:
                    search_filter = Filter(
                        property_name="lastmodifieddate",
                        operator="GTE",
                        value=str(last_modified_after_ms),
                    )
                    filter_group = FilterGroup(filters=[search_filter])
                    search_request = PublicObjectSearchRequest(
                        properties=properties,
                        limit=self._page_size,
                        after=after,
                        filter_groups=[filter_group],
                        sorts=["lastmodifieddate"],
                    )
                    page = cast(
                        CollectionResponseWithTotalSimplePublicObjectForwardPaging,
                        self._client.crm.objects.search_api.do_search(
                            object_type=object_type,
                            associations=(associations or [])
                            if self._include_associations
                            else [],
                            public_object_search_request=search_request,
                        ),
                    )

                results = [record.to_dict() for record in (page.results or [])]
                if len(results) > 0:
                    yield results
                if page.paging is None or page.paging.next is None:
                    break
                after = page.paging.next.after
        except ApiException as e:
            logger.error(f"Failed to retrieve paginated-list of {object_type}: {e}")
            raise HubSpotClientError(
                f"Failed to retrieve paginated-list of {object_type}: {e}"
            )

    def validate_auth(self) -> bool:
        """Validates the underlying access token against HubSpot.

        Always makes a real HTTP request, unlike `ping()`. Intended for
        startup checks where a stale cached result isn't acceptable.

        Returns:
            True if the token is valid.

        Raises:
            UnauthorizedError: If the token is invalid, revoked, or scoped
                to the wrong portal.
        """
        return self._auth.validate()

    def ping(self) -> bool:
        """Checks whether HubSpot is reachable, favoring a cached result.

        Uses `HubSpotAuth`'s cached validation state (up to 5 minutes old)
        to avoid making a network call on every health check. Falls back
        to a real validation call when the cache is stale, and never
        raises — failures are logged and reported as False.

        Returns:
            True if HubSpot is reachable and authenticated; False otherwise.
        """
        if self._auth.is_authenticated(max_age_seconds=300):
            return True

        try:
            return self.validate_auth()
        except Exception as e:
            logger.warning(f"HubSpot ping failed: {e}")
            return False
