import json
from collections.abc import Iterator
from typing import Any, cast

import requests
from hubspot import HubSpot
from hubspot.crm.objects import (
    ApiException,
    CollectionResponseSimplePublicObjectWithAssociationsForwardPaging,
    CollectionResponseWithTotalSimplePublicObjectForwardPaging,
)
from hubspot.crm.objects.models import Filter, FilterGroup, PublicObjectSearchRequest
from hubspot.crm.owners import ApiException as OwnersApiException
from hubspot.crm.owners import CollectionResponsePublicOwnerForwardPaging
from urllib3.util.retry import Retry

from app.auth.hubspot_auth import HubSpotAuth
from app.logger import logger


class HubSpotClientError(Exception):
    """Raised when a HubSpot API request fails after all retries are exhausted."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class HubSpotClient:
    """Client for HubSpot API."""

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
        associations: list[str] | None = None,
        last_modified_after_ms: int | None = None,
        after: str | None = None,
    ) -> Iterator[tuple[str | None, list[dict]]]:
        """Iterates over HubSpot objects with cursor checkpoint support.

        Args:
            object_type: HubSpot object type (e.g. "contacts").
            properties: Properties to request.
            associations: Optional association types.
            last_modified_after_ms: Incremental extraction timestamp.
            after: Optional HubSpot paging cursor to resume from.

        Yields:
            Tuples of (next_cursor, records).

            `next_cursor` should be persisted only after the page has been
            successfully processed. It will be None for the final page.
        """
        try:
            current_after = after
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
                            after=current_after,
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
                        after=current_after,
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
                next_after: str | None = None
                if page.paging is not None and page.paging.next is not None:
                    next_after = page.paging.next.after

                if results:
                    yield next_after, results

                if next_after is None:
                    break

                current_after = next_after

        except ApiException as e:
            logger.error(f"Failed to retrieve paginated-list of {object_type}: {e}")
            raise HubSpotClientError(
                f"Failed to retrieve paginated-list of {object_type}: {e}"
            ) from e

    def iter_owners(
        self, after: str | None = None
    ) -> Iterator[tuple[str | None, list[dict]]]:
        """Iterates over HubSpot owners (users assignable as record owners).

        Uses the dedicated Owners API (`/crm/v3/owners`), not the generic
        CRM objects endpoint `iter_objects` uses - owners have no
        `properties`/associations model, and the API supports neither
        the Search API nor incremental (`last_modified_after_ms`)
        filtering. Each owner is reshaped into the same
        `{"id": ..., "properties": {...}}` structure `iter_objects`
        yields, so owners can flow through the same normalization,
        storage, and checkpointing pipeline as any other object type
        without those callers needing to know the difference.

        Args:
            after: Optional HubSpot paging cursor to resume from.

        Yields:
            Tuples of (next_cursor, records), matching `iter_objects`.
            `next_cursor` will be None for the final page.
        """
        try:
            current_after = after
            while True:
                page = cast(
                    CollectionResponsePublicOwnerForwardPaging,
                    self._client.crm.owners.owners_api.get_page(
                        after=current_after,
                        limit=self._page_size,
                    ),
                )

                results = [
                    {
                        "id": owner.id,
                        "properties": {
                            "email": owner.email,
                            "firstName": owner.first_name,
                            "lastName": owner.last_name,
                            "userId": owner.user_id,
                            "createdAt": owner.created_at.isoformat()
                            if owner.created_at
                            else None,
                            "updatedAt": owner.updated_at.isoformat()
                            if owner.updated_at
                            else None,
                            "archived": owner.archived,
                        },
                    }
                    for owner in (page.results or [])
                ]

                next_after: str | None = None
                if page.paging is not None and page.paging.next is not None:
                    next_after = page.paging.next.after

                if results:
                    yield next_after, results

                if next_after is None:
                    break

                current_after = next_after

        except OwnersApiException as e:
            logger.error(f"Failed to retrieve paginated-list of owners: {e}")
            raise HubSpotClientError(
                f"Failed to retrieve paginated-list of owners: {e}"
            ) from e

    def iter_engagements(
        self, after: str | None = None
    ) -> Iterator[tuple[str | None, list[dict]]]:
        """Iterates over HubSpot engagements (calls, emails, meetings, notes, tasks).

        Uses the legacy v1 Engagements API (`/engagements/v1/engagements/paged`)
        via a raw HTTP call, since this endpoint predates and isn't
        covered by the `hubspot-api-client` SDK. Like `iter_owners`,
        engagements don't fit the standard CRM objects
        properties/associations model, and this endpoint paginates by
        numeric offset rather than a cursor token - the offset is
        stringified for `after`/the yielded cursor, to keep the same
        `str | None` contract every other `iter_*` method uses.

        Each engagement's nested `engagement`/`associations`/`metadata`
        blob is reshaped into the same `{"id", "properties",
        "associations"}` structure `iter_objects` yields. `metadata`'s
        shape varies by engagement type (email/call/meeting/note/task
        each have different fields), so it's kept as a single
        JSON-string property rather than flattened.

        Args:
            after: Optional numeric offset (as a string) to resume from.

        Yields:
            Tuples of (next_offset, records), matching `iter_objects`.
            `next_offset` will be None once HubSpot reports no more
            results (`hasMore: false`).
        """
        try:
            offset = int(after) if after is not None else None
            while True:
                params: dict[str, Any] = {"limit": self._page_size}
                if offset is not None:
                    params["offset"] = offset

                response = requests.get(
                    url=f"{self._auth.base_url.rstrip('/')}/engagements/v1/engagements/paged",
                    headers=self._auth.get_headers(),
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    engagement = item.get("engagement", {})
                    associations = item.get("associations", {})
                    metadata = item.get("metadata", {})
                    results.append(
                        {
                            "id": str(engagement.get("id")),
                            "properties": {
                                "type": engagement.get("type"),
                                "createdAt": engagement.get("createdAt"),
                                "lastUpdated": engagement.get("lastUpdated"),
                                "ownerId": engagement.get("ownerId"),
                                "timestamp": engagement.get("timestamp"),
                                "metadata": json.dumps(metadata),
                            },
                            "associations": {
                                "contacts": [
                                    str(i) for i in associations.get("contactIds", [])
                                ],
                                "companies": [
                                    str(i) for i in associations.get("companyIds", [])
                                ],
                                "deals": [
                                    str(i) for i in associations.get("dealIds", [])
                                ],
                            },
                        }
                    )

                has_more = data.get("hasMore", False)
                next_offset = str(data["offset"]) if has_more else None

                if results:
                    yield next_offset, results

                if next_offset is None:
                    break

                offset = int(next_offset)

        except requests.RequestException as e:
            logger.error(f"Failed to retrieve paginated-list of engagements: {e}")
            raise HubSpotClientError(
                f"Failed to retrieve paginated-list of engagements: {e}"
            ) from e

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
        except Exception as e:  # noqa: BLE001
            logger.warning(f"HubSpot ping failed: {e}")
            return False

    def get_portal_info(self) -> dict:
        """Fetches HubSpot portal metadata.

        Returns:
            The raw account-info response (portalId, uiDomain,
            dataHostingLocation, timeZone, etc.)

        Raises:
            HubSpotClientError: If the request fails.
        """
        try:
            response = requests.get(
                url=f"{self._auth.base_url.rstrip('/')}/account-info/{self._auth.api_version}/details",
                headers=self._auth.get_headers(),
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise HubSpotClientError(f"Failed to fetch portal info: {e}") from e

    def get_api_usage(self) -> dict:
        """Fetches current daily API usage and limits for this private app.

        Returns:
            The first entry from the account-info daily usage endpoint's
            `results` array (usageLimit, currentUsage, collectedAt, etc.)

        Raises:
            HubSpotClientError: If the request fails or returns no results.
        """
        try:
            response = requests.get(
                url=f"{self._auth.base_url.rstrip('/')}/account-info/{self._auth.api_version}/api-usage/daily/private-apps",
                headers=self._auth.get_headers(),
                timeout=10,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                raise HubSpotClientError("No API usage data returned")
            return results[0]
        except requests.RequestException as e:
            raise HubSpotClientError(f"Failed to fetch API usage: {e}") from e
