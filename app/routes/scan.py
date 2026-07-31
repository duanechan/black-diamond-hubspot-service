import uuid
from datetime import datetime

from flask import current_app, request
from flask_restx import Namespace, Resource, fields

from app.auth.hmac_auth import require_hmac
from app.config import Settings
from app.constants import SUPPORTED_OBJECTS
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
    @scan_ns.marshal_with(scan_start_response)
    @scan_ns.response(202, "Scan started")
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
