from flask import current_app
from flask_restx import Namespace, Resource, fields

from app.clients.hubspot_client import HubSpotClient
from app.config import Settings
from app.storage.clickhouse_client import ClickHouseClient
from app.storage.kafka_producer import KafkaProducer
from app.storage.minio_client import MinioClient

health_ns = Namespace("health", description="Service health checks")

health_response = health_ns.model(
    "HealthResponse",
    {
        "status": fields.String(
            description="Overall service status",
            enum=["healthy", "degraded"],
        ),
        "service": fields.String(description="Service name"),
        "version": fields.String(description="Service version"),
        "hubspot_connected": fields.Boolean(description="Whether HubSpot is reachable"),
        "minio_connected": fields.Boolean(description="Whether MinIO is reachable"),
        "kafka_connected": fields.Boolean(description="Whether Kafka is reachable"),
        "clickhouse_connected": fields.Boolean(
            description="Whether ClickHouse is reachable"
        ),
    },
)


@health_ns.route("/")
class Health(Resource):
    @health_ns.marshal_with(health_response)
    @health_ns.response(200, "Service is healthy")
    @health_ns.response(503, "Service is degraded")
    def get(self):
        settings: Settings = current_app.extensions["settings"]
        client: HubSpotClient = current_app.extensions["client"]
        minio: MinioClient = current_app.extensions["minio"]
        kafka: KafkaProducer = current_app.extensions["kafka"]
        clickhouse: ClickHouseClient = current_app.extensions["clickhouse"]

        is_hubspot_ok = client.ping()
        is_minio_ok = minio.ping()
        is_kafka_ok = kafka.ping()
        is_clickhouse_ok = clickhouse.ping()
        is_healthy = is_hubspot_ok and is_minio_ok and is_kafka_ok and is_clickhouse_ok

        return {
            "status": "healthy" if is_healthy else "degraded",
            "service": settings.APP_TITLE,
            "version": settings.APP_VERSION,
            "hubspot_connected": is_hubspot_ok,
            "minio_connected": is_minio_ok,
            "kafka_connected": is_kafka_ok,
            "clickhouse_connected": is_clickhouse_ok,
        }, 200 if is_healthy else 503
