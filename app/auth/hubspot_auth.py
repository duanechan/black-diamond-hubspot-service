from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from app.logger import logger


class UnauthorizedError(ValueError):
    "Raised when status code is 401 Unauthorized."

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class HubSpotAuth:
    """Manages HubSpot API authentication.

    Builds the auth headers used for HubSpot API requests and validates
    the configured access token/portal against HubSpot at startup.
    """

    def __init__(
        self,
        base_url: str,
        api_version: str,
        access_token: str,
        portal_id: str,
    ) -> None:
        self.base_url = base_url
        self.api_version = api_version
        self._access_token = access_token
        self._portal_id = portal_id
        self._request_timeout = 10
        self._is_authenticated = False
        self._last_validated_at: Optional[datetime] = None

    @property
    def access_token(self) -> str:
        return self._access_token

    def get_headers(self) -> dict[str, str]:
        """Returns standard auth headers for HubSpot API requests.

        Returns:
            The auth headers with the `_access_token` and the content type set to `application/json`.
        """
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def validate(self) -> bool:
        """Validates the HubSpot access token against the account-info endpoint.

        Confirms the token is accepted by HubSpot and that it belongs to the
        expected portal (HUBSPOT_PORTAL_ID). Called once at startup — fails
        fast if the token is invalid, revoked, or scoped to the wrong portal.

        Returns:
            True if the token is valid and matches the configured portal.

        Raises:
            UnauthorizedError: If the token is invalid/revoked, or if the
                token's portal does not match HUBSPOT_PORTAL_ID.
        """
        response = requests.get(
            url=f"{self.base_url.rstrip('/')}/account-info/{self.api_version}/details",
            headers=self.get_headers(),
            timeout=self._request_timeout,
        )
        if response.status_code == 401:
            self._set_authenticated(False)
            raise UnauthorizedError(
                "'HUBSPOT_ACCESS_TOKEN' is invalid or revoked. "
                "Generate a new service key in HubSpot: Settings -> Development -> Keys -> Service Keys"
            )

        response.raise_for_status()
        data = response.json()

        portal_id = str(data.get("portalId", ""))
        if self._portal_id != portal_id:
            self._set_authenticated(False)
            raise UnauthorizedError(
                "'HUBSPOT_PORTAL_ID' does not match the 'portalId' response field. "
                "Verify the portal ID of the HubSpot account in use."
            )

        self._set_authenticated(True)

        logger.info(
            f"HubSpot token validated. Portal: {portal_id} ({data.get('uiDomain', '-')})"
        )
        return True

    def is_authenticated(self, max_age_seconds: int = 60) -> bool:
        """Reports whether the token was successfully validated recently.

        Reads cached state from the last `validate()` call rather than making
        a new HTTP request — use this to avoid redundant network calls (e.g.
        from frequent health checks). Does not re-validate; if the cached
        result is stale (older than `max_age_seconds`) or validation has
        never run, this returns False rather than checking HubSpot again.

        Args:
            max_age_seconds: How long a previous successful validation stays
                trusted before being considered stale. Defaults to 60.

        Returns:
            True if the last `validate()` call succeeded and happened within
            `max_age_seconds`; False otherwise (including if `validate()`
            has never been called).
        """
        last_validated_at = self._last_validated_at
        if not self._is_authenticated or last_validated_at is None:
            return False
        age = datetime.now(timezone.utc) - last_validated_at
        return age <= timedelta(seconds=max_age_seconds)

    def _set_authenticated(self, is_authenticated: bool) -> None:
        """Records the outcome of a validation attempt.

        Updates both the authenticated flag and the timestamp used by
        `is_authenticated()` to judge staleness. Called from every exit
        path of `validate()` — success and both failure cases — so the
        two fields always change together and never drift out of sync.

        Args:
            is_authenticated: Whether the just-completed validation attempt
                succeeded.
        """
        self._is_authenticated = is_authenticated
        self._last_validated_at = datetime.now(timezone.utc)
