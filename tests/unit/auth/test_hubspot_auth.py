from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.auth.hubspot_auth import HubSpotAuth, UnauthorizedError


def make_auth():
    return HubSpotAuth(
        base_url="https://api.hubapi.com",
        api_version="v3",
        access_token="secret-token",
        portal_id="12345",
    )


class TestGetHeaders:
    def test_includes_bearer_token_and_content_type(self):
        auth = make_auth()

        headers = auth.get_headers()

        assert headers["Authorization"] == "Bearer secret-token"
        assert headers["Content-Type"] == "application/json"


class TestValidate:
    def test_success_returns_true_and_marks_authenticated(self):
        auth = make_auth()
        response = MagicMock(status_code=200)
        response.json.return_value = {"portalId": 12345, "uiDomain": "app.hubspot.com"}

        with patch("app.auth.hubspot_auth.requests.get", return_value=response):
            result = auth.validate()

        assert result is True
        assert auth.is_authenticated() is True

    def test_401_raises_unauthorized_and_marks_unauthenticated(self):
        auth = make_auth()
        response = MagicMock(status_code=401)

        with (
            patch("app.auth.hubspot_auth.requests.get", return_value=response),
            pytest.raises(UnauthorizedError, match="invalid or revoked"),
        ):
            auth.validate()

        assert auth.is_authenticated() is False

    def test_portal_id_mismatch_raises_unauthorized(self):
        auth = make_auth()
        response = MagicMock(status_code=200)
        response.json.return_value = {"portalId": 99999}

        with (
            patch("app.auth.hubspot_auth.requests.get", return_value=response),
            pytest.raises(UnauthorizedError, match="HUBSPOT_PORTAL_ID"),
        ):
            auth.validate()

        assert auth.is_authenticated() is False

    def test_portal_id_mismatch_still_marks_unauthenticated_after_prior_success(self):
        """A previously-successful validation must not leave stale True
        state if a later validate() call fails."""
        auth = make_auth()
        ok_response = MagicMock(status_code=200)
        ok_response.json.return_value = {"portalId": 12345}
        with patch("app.auth.hubspot_auth.requests.get", return_value=ok_response):
            auth.validate()
        assert auth.is_authenticated() is True

        bad_response = MagicMock(status_code=200)
        bad_response.json.return_value = {"portalId": 99999}
        with (
            patch("app.auth.hubspot_auth.requests.get", return_value=bad_response),
            pytest.raises(UnauthorizedError),
        ):
            auth.validate()

        assert auth.is_authenticated() is False

    def test_other_http_error_propagates_not_swallowed(self):
        """A 500 (or similar) should raise via raise_for_status(), not be
        silently caught or misreported as an UnauthorizedError."""
        auth = make_auth()
        response = MagicMock(status_code=500)
        response.raise_for_status.side_effect = requests.HTTPError("server error")

        with (
            patch("app.auth.hubspot_auth.requests.get", return_value=response),
            pytest.raises(requests.HTTPError),
        ):
            auth.validate()


class TestIsAuthenticated:
    def test_false_before_any_validate_call(self):
        auth = make_auth()
        assert auth.is_authenticated() is False

    def test_false_once_max_age_exceeded(self):
        auth = make_auth()
        response = MagicMock(status_code=200)
        response.json.return_value = {"portalId": 12345}
        with patch("app.auth.hubspot_auth.requests.get", return_value=response):
            auth.validate()

        # Backdate the cached validation past the staleness window.
        auth._last_validated_at = datetime.now(UTC) - timedelta(seconds=120)

        assert auth.is_authenticated(max_age_seconds=60) is False

    def test_true_within_max_age(self):
        auth = make_auth()
        response = MagicMock(status_code=200)
        response.json.return_value = {"portalId": 12345}
        with patch("app.auth.hubspot_auth.requests.get", return_value=response):
            auth.validate()

        auth._last_validated_at = datetime.now(UTC) - timedelta(seconds=30)

        assert auth.is_authenticated(max_age_seconds=60) is True
