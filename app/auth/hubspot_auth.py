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
        self._auth_url = f"{base_url.rstrip('/')}/account-info/{api_version}/details"
        self._access_token = access_token
        self._portal_id = portal_id
        self._request_timeout = 10

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
            url=self._auth_url,
            headers=self.get_headers(),
            timeout=self._request_timeout,
        )
        if response.status_code == 401:
            raise UnauthorizedError(
                "'HUBSPOT_ACCESS_TOKEN' is invalid or revoked. "
                "Generate a new service key in HubSpot: Settings -> Development -> Keys -> Service Keys"
            )

        response.raise_for_status()
        data = response.json()

        portal_id = str(data.get("portalId", ""))
        if self._portal_id != portal_id:
            raise UnauthorizedError(
                "'HUBSPOT_PORTAL_ID' does not match the 'portalId' response field. "
                "Verify the portal ID of the HubSpot account in use."
            )

        logger.info(
            f"HubSpot token validated. Portal: {portal_id} ({data.get('uiDomain', '-')})"
        )
        return True
