from app.clients.hubspot_client import HubSpotClientError


class TestBatchInfo:
    def test_returns_portal_and_usage_info(self, app, client):
        hs_client = app.extensions["client"]
        hs_client.get_portal_info.return_value = {
            "portalId": 12345,
            "uiDomain": "app.hubspot.com",
            "dataHostingLocation": "na1",
            "timeZone": "America/New_York",
        }
        hs_client.get_api_usage.return_value = {
            "name": "private-apps",
            "usageLimit": 250000,
            "currentUsage": 42,
            "collectedAt": "2026-08-17T00:00:00Z",
        }

        resp = client.get("/api/batch/info")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["token_status"] == "valid"
        assert body["portal"]["portal_id"] == "12345"
        assert body["api_limits"]["daily_api_requests"]["usage_limit"] == 250000

    def test_hubspot_error_returns_502(self, app, client):
        app.extensions["client"].get_portal_info.side_effect = HubSpotClientError(
            "token revoked"
        )

        resp = client.get("/api/batch/info")

        assert resp.status_code == 502
        assert resp.get_json()["token_status"] == "invalid"
