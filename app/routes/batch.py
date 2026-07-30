from flask import current_app
from flask_restx import Namespace, Resource

from app.auth.hmac_auth import require_hmac
from app.clients.hubspot_client import HubSpotClient, HubSpotClientError

batch_ns = Namespace("batch", description="HubSpot portal and API quota info")


@batch_ns.route("/info")
class Info(Resource):
    @require_hmac()
    def get(self):
        client: HubSpotClient = current_app.extensions["client"]
        try:
            portal = client.get_portal_info()
            usage = client.get_api_usage()
        except HubSpotClientError as e:
            return {
                "token_status": "invalid",
                "error": str(e),
            }, 502

        return {
            "portal": {
                "portal_id": str(portal.get("portalId", "")),
                "ui_domain": portal.get("uiDomain"),
                "data_hosting_location": portal.get("dataHostingLocation"),
                "time_zone": portal.get("timeZone"),
            },
            "api_limits": {
                "daily_api_requests": {
                    "name": usage.get("name"),
                    "usage_limit": usage.get("usageLimit"),
                    "current_usage": usage.get("currentUsage"),
                    "fetch_date": usage.get("collectedAt"),
                }
            },
            "token_status": "valid",
        }, 200
