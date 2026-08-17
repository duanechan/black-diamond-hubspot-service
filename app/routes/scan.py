import uuid
from datetime import datetime

from flask import current_app, request
from flask_restx import Namespace, Resource, fields

from app.auth.hmac_auth import require_hmac
from app.config import Settings
from app.constants import SUPPORTED_OBJECTS
from app.repositories.scan_repository import ScanNotFoundError
from app.services.extraction_service import ExtractionService

scan_ns = Namespace("scan", description="Scan operations")

scan_start_request = scan_ns.model(
    "StartScanRequest",
    {
        "scan_id": fields.String(description="Scan ID"),
        "org_id": fields.String(description="Organization ID"),
        "objects": fields.List(fields.String, description="List of supported objects"),
        "filters": fields.Raw(description="Filters"),
        "output_format": fields.String(
            description="Output format", enum=["parquet", "json"]
        ),
        "include_associations": fields.Boolean(
            description="Whether to include associations"
        ),
        "destination": fields.Raw(description="Destination to store the results in"),
    },
)

scan_start_response = scan_ns.model(
    "ScanStartResponse",
    {
        "success": fields.Boolean(),
        "scan_id": fields.String(),
        "status": fields.String(),
        "extractions": fields.Raw(),
        "message": fields.String(),
    },
)


@scan_ns.route("/start")
class Start(Resource):
    @scan_ns.expect(scan_start_request)
    @scan_ns.response(202, "Scan started", scan_start_response)
    @scan_ns.response(400, "Bad Request")
    @require_hmac()
    def post(self):
        settings: Settings = current_app.extensions["settings"]
        data = request.get_json()
        scan_id = data.get("scan_id")
        org_id = data.get("org_id")
        object_types = data.get("objects", [])
        filters = data.get("filters", {})
        include_associations = data.get(
            "include_associations", settings.HUBSPOT_INCLUDE_ASSOCIATIONS
        )
        output_format = data.get("output_format", "parquet")
        destination = data.get(
            "destination",
            {
                "minio_bucket": settings.MINIO_BUCKET,
                "kafka_publish": True,
                "clickhouse_load": False,
            },
        )

        last_modified_after = filters.get("last_modified_after")
        last_modified_after_ms = (
            int(datetime.fromisoformat(last_modified_after).timestamp() * 1000)
            if last_modified_after is not None
            else None
        )

        missing_fields = []
        if scan_id is None:
            missing_fields.append("scan_id")
        if org_id is None:
            missing_fields.append("org_id")
        if len(object_types) == 0:
            missing_fields.append("objects")

        if len(missing_fields) > 0:
            return {
                "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
                "error": "Invalid request body",
                "fields": build_validation_errors(missing_fields),
            }, 400

        es: ExtractionService = current_app.extensions["extraction_service"]

        try:
            es.validate_scan_params(output_format, destination)
        except (ValueError, NotImplementedError) as e:
            return {
                "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
                "error": str(e),
            }, 400

        properties_by_object = {
            object_type: SUPPORTED_OBJECTS.get(object_type, {}).get(
                "default_properties", []
            )
            for object_type in object_types
        }
        associations_by_object = {
            object_type: SUPPORTED_OBJECTS.get(object_type, {}).get(
                "association_targets", []
            )
            if include_associations
            else []
            for object_type in object_types
        }

        scans = current_app.extensions["scans"]
        scans.create(
            scan_id=scan_id,
            org_id=org_id,
            config={
                "object_types": object_types,
                "filters": filters,
                "output_format": output_format,
                "destination": destination,
            },
        )

        es.start_scan_async(
            scan_id=scan_id,  # pyright: ignore[reportArgumentType]
            org_id=org_id,  # pyright: ignore[reportArgumentType]
            object_types=object_types,
            properties_by_object=properties_by_object,
            associations_by_object=associations_by_object,
            last_modified_after_ms=last_modified_after_ms,
            output_format=output_format,
            destination=destination,
        )

        return {
            "success": True,
            "scan_id": scan_id,
            "status": "started",
            "extractions": {
                object_type: {"status": "in_progress", "cursor": None}
                for object_type in object_types
            },
            "message": (
                f"{len(object_types)} HubSpot extraction jobs started. "
                f"Poll /api/scan/{scan_id}/status for progress."
            ),
        }, 202


def build_validation_errors(missing_fields: list[str]) -> dict[str, dict[str, str]]:
    FIELD_ERRORS = {
        "scan_id": {
            "error": "`scan_id` not provided",
            "fix": "Set the `scan_id` field to a UUID (v4) string in the request body.",
        },
        "org_id": {
            "error": "`org_id` not provided",
            "fix": "Set the `org_id` field to the organization ID.",
        },
        "objects": {
            "error": "`objects` list is empty",
            "fix": "Specify the objects to be extracted ('contacts', 'leads', e.g.).",
        },
    }
    return {
        field: FIELD_ERRORS.get(field, {"error": "Unknown error"})
        for field in missing_fields
    }


@scan_ns.route("/<string:scan_id>/status")
class Status(Resource):
    @require_hmac()
    def get(self, scan_id: str):
        scans = current_app.extensions["scans"]
        try:
            scan = scans.get(scan_id)
        except ScanNotFoundError:
            return {"error": f"Scan '{scan_id}' not found"}, 404

        totals = {
            "objects_total": len(scan.progress),
            "objects_complete": sum(
                1 for e in scan.progress.values() if e.get("status") == "complete"
            ),
            "objects_failed": sum(
                1 for e in scan.progress.values() if e.get("status") == "failed"
            ),
            "records_extracted": sum(
                e.get("records_extracted", 0) for e in scan.progress.values()
            ),
        }

        return {
            "scan_id": scan.scan_id,
            "org_id": scan.org_id,
            "status": scan.status,
            "started_at": scan.started_at.isoformat(),
            "updated_at": scan.updated_at.isoformat(),
            "progress": scan.progress,
            "totals": totals,
        }, 200


@scan_ns.route("/<string:scan_id>/cancel")
class Cancel(Resource):
    @require_hmac()
    def post(self, scan_id: str):
        scans = current_app.extensions["scans"]
        es: ExtractionService = current_app.extensions["extraction_service"]

        try:
            scan = scans.get(scan_id)
        except ScanNotFoundError:
            return {"error": f"Scan '{scan_id}' not found"}, 404

        already_complete = [
            object_type
            for object_type, entry in scan.progress.items()
            if entry.get("status") == "complete"
        ]

        cancelled = es.cancel_scan(scan_id)
        if not cancelled:
            return {
                "success": False,
                "scan_id": scan_id,
                "status": scan.status,
                "message": "Scan is not currently running (already finished or not found).",
            }, 400

        pending = [ot for ot in scan.progress if ot not in already_complete]

        return {
            "success": True,
            "scan_id": scan_id,
            "status": "cancelled",
            "objects_cancelled": pending,
            "objects_already_complete": already_complete,
            "message": (
                f"Scan cancelled. {len(already_complete)} object(s) "
                f"({', '.join(already_complete) or 'none'}) completed before cancellation."
            ),
        }, 200


@scan_ns.route("/list")
class List(Resource):
    @require_hmac()
    def get(self):
        scans_repo = current_app.extensions["scans"]
        org_id = request.args.get("org_id")
        status = request.args.get("status")

        scans = scans_repo.list(org_id=org_id, status=status)

        return {
            "scans": [
                {
                    "scan_id": scan.scan_id,
                    "org_id": scan.org_id,
                    "status": scan.status,
                    "started_at": scan.started_at.isoformat(),
                    "updated_at": scan.updated_at.isoformat(),
                }
                for scan in scans
            ],
            "count": len(scans),
        }, 200


@scan_ns.route("/<string:scan_id>/remove")
class Remove(Resource):
    @require_hmac()
    def delete(self, scan_id: str):
        scans_repo = current_app.extensions["scans"]
        try:
            scans_repo.delete(scan_id)
        except ScanNotFoundError:
            return {"error": f"Scan '{scan_id}' not found"}, 404

        return {
            "success": True,
            "scan_id": scan_id,
            "message": "Scan record removed.",
        }, 200


@scan_ns.route("/statistics")
class Statistics(Resource):
    @require_hmac()
    def get(self):
        scans_repo = current_app.extensions["scans"]
        org_id = request.args.get("org_id")
        all_scans = scans_repo.list(org_id=org_id)

        by_status: dict[str, int] = {}
        total_records = 0
        for scan in all_scans:
            by_status[scan.status] = by_status.get(scan.status, 0) + 1
            total_records += sum(
                entry.get("records_extracted", 0) for entry in scan.progress.values()
            )

        return {
            "total_scans": len(all_scans),
            "by_status": by_status,
            "total_records_extracted": total_records,
        }, 200


@scan_ns.route("/<string:scan_id>/resume")
class Resume(Resource):
    @require_hmac()
    def post(self, scan_id: str):
        settings: Settings = current_app.extensions["settings"]
        scans = current_app.extensions["scans"]
        es: ExtractionService = current_app.extensions["extraction_service"]

        try:
            scan = scans.get(scan_id)
        except ScanNotFoundError:
            return {"error": f"Scan '{scan_id}' not found"}, 404

        if scan.status not in ("failed", "cancelled"):
            return {
                "success": False,
                "scan_id": scan_id,
                "status": scan.status,
                "message": f"Scan is '{scan.status}', not failed or cancelled - nothing to resume.",
            }, 400

        config = scan.config
        object_types = config.get("object_types", [])
        incomplete_types = [
            object_type
            for object_type in object_types
            if scan.progress.get(object_type, {}).get("status") != "complete"
        ]

        if len(incomplete_types) == 0:
            return {
                "success": False,
                "scan_id": scan_id,
                "status": scan.status,
                "message": "All object types already completed - nothing to resume.",
            }, 400

        filters = config.get("filters", {})
        output_format = config.get("output_format", "parquet")
        destination = config.get("destination", {})
        include_associations = config.get(
            "include_associations", settings.HUBSPOT_INCLUDE_ASSOCIATIONS
        )

        last_modified_after = filters.get("last_modified_after")
        last_modified_after_ms = (
            int(datetime.fromisoformat(last_modified_after).timestamp() * 1000)
            if last_modified_after is not None
            else None
        )

        properties_by_object = {
            object_type: SUPPORTED_OBJECTS.get(object_type, {}).get(
                "default_properties", []
            )
            for object_type in incomplete_types
        }
        associations_by_object = {
            object_type: SUPPORTED_OBJECTS.get(object_type, {}).get(
                "association_targets", []
            )
            if include_associations
            else []
            for object_type in incomplete_types
        }
        after_by_object = {
            object_type: scan.progress.get(object_type, {}).get("cursor")
            for object_type in incomplete_types
        }

        scans.update_status(scan_id, "started")

        es.start_scan_async(
            scan_id=scan_id,
            org_id=scan.org_id,
            object_types=incomplete_types,
            properties_by_object=properties_by_object,
            associations_by_object=associations_by_object,
            last_modified_after_ms=last_modified_after_ms,
            output_format=output_format,
            destination=destination,
            after_by_object=after_by_object,
        )

        return {
            "success": True,
            "scan_id": scan_id,
            "status": "started",
            "resumed_objects": incomplete_types,
            "message": f"Resuming {len(incomplete_types)} incomplete object type(s).",
        }, 202
