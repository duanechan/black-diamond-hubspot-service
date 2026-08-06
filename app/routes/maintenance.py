from datetime import UTC, datetime, timedelta

from flask import current_app, request
from flask_restx import Namespace, Resource

from app.auth.hmac_auth import require_hmac
from app.config import Settings

maintenance_ns = Namespace("maintenance", description="Maintenance operations")


@maintenance_ns.route("/cleanup")
class Cleanup(Resource):
    @require_hmac(requires_engineer_key=True)
    def post(self):
        settings: Settings = current_app.extensions["settings"]
        scans = current_app.extensions["scans"]

        older_than_days = request.args.get(
            "older_than_days", settings.CLEANUP_DAYS, type=int
        )
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        deleted_count = scans.delete_older_than(cutoff)

        return {
            "success": True,
            "deleted_count": deleted_count,
            "older_than_days": older_than_days,
            "cutoff": cutoff.isoformat(),
            "message": f"Removed {deleted_count} scan record(s) older than {older_than_days} day(s).",
        }, 200
