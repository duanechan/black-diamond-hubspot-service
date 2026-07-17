from datetime import datetime

from flask import current_app, request
from flask_restx import Namespace, Resource, fields

from app.services.extraction_service import ExtractionService

scan_ns = Namespace("scan", description="Scan operations")

scan_start_request = scan_ns.model(
    "StartScanRequest",
    {
        "scan_id": fields.String(description="Scan ID"),
        "org_id": fields.String(description="Organization ID"),
        "objects": fields.List(
            fields.String,
            description="List of supported objects",
        ),
        "filters": fields.Raw(
            description="Filters",
        ),  # {"last_modified_after": "2026-01-01T00:00:00Z"}
        "output_format": fields.String(
            description="Output format",
            enum=["parquet", "json"],
        ),
        "include_associations": fields.Boolean(
            description="Whether to include associations"
        ),
        "destination": fields.Raw(
            description="Destination to store the results in",
        ),
        # {
        #     "minio_bucket": "hubspot-extracts",
        #     "kafka_publish": true,
        #     "clickhouse_load": false,
        # },
    },
)

scan_start_response = scan_ns.model(
    "ScanStartResponse",
    {
        "success": fields.Boolean(description="Whether the request is successful"),
        "scan_id": fields.String(description="Scan ID"),
        "org_id": fields.String(description="Organization ID"),
        "extractions": fields.Raw(description="Per-object-type extraction results"),
        "message": fields.String(description="Response message"),
    },
)


@scan_ns.route("/start")
class Start(Resource):
    @scan_ns.expect(scan_start_request)
    @scan_ns.marshal_with(scan_start_response)
    @scan_ns.response(202, "Successful")
    @scan_ns.response(400, "Bad Request")
    def post(self):
        data = request.get_json()
        scan_id = data.get("scan_id")
        org_id = data.get("org_id")
        object_types = data.get("objects", [])
        filters = data.get("filters", {})
        include_associations = data.get("include_associations", True)
        output_format = data.get("output_format", "parquet")
        destination = data.get(
            "destination",
            {
                "minio_bucket": "REPLACE_WITH_MINO_BUCKET",
                "kafka_publish": True,
                "clickhouse_load": False,
            },
        )

        if scan_id is None or org_id is None or len(object_types) == 0:
            return {}, 400

        es: ExtractionService = current_app.extensions["extraction_service"]
        extractions = es.start_scan(
            object_types=object_types,
            properties_by_object={},
            last_modified_after_ms=int(
                datetime.fromisoformat(filters.get("last_modified_after")).timestamp()
            ),
        )
        success = all(e["status"] == "completed" for e in extractions.values())
        return {
            "success": success,
            "scan_id": data["scan_id"],
            "org_id": data["org_id"],
            "extractions": extractions,
            "message": "Scan completed" if success else "Scan completed with failures",
        }, 202
