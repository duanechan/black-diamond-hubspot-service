from flask import Blueprint, current_app

from app.clients.hubspot_client import HubSpotClient
from app.config import Settings

health_bp = Blueprint("health", __name__, url_prefix="/api/health")


@health_bp.route("/")
def health():
    settings: Settings = current_app.extensions["settings"]
    client: HubSpotClient = current_app.extensions["client"]

    is_hubspot_ok = client.ping()
    is_minio_ok = False
    is_kafka_ok = False
    is_healthy = is_hubspot_ok and is_minio_ok and is_kafka_ok

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "hubspot_connected": is_hubspot_ok,
        "minio_connected": is_minio_ok,
        "kafka_connected": is_kafka_ok,
    }, 200 if is_healthy else 503
