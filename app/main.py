from flask import Flask
from flask_restx.api import Api

from app.auth.hubspot_auth import HubSpotAuth
from app.clients.hubspot_client import HubSpotClient
from app.config import Settings, validate_settings
from app.db import create_db_engine, create_session_factory
from app.logger import logger, werkzeug_logger
from app.models.base import Base
from app.repositories.scan_repository import ScanRepository
from app.routes.batch import batch_ns
from app.routes.health import health_ns
from app.routes.key import key_ns
from app.routes.maintenance import maintenance_ns
from app.routes.objects import objects_ns
from app.routes.scan import scan_ns
from app.services.extraction_service import ExtractionService
from app.services.normalization_service import NormalizationService
from app.services.pii_service import PIIService
from app.storage.clickhouse_client import ClickHouseClient
from app.storage.kafka_producer import KafkaProducer
from app.storage.minio_client import MinioClient


def create_app(settings: Settings) -> Flask:
    werkzeug_logger.setLevel(settings.LOG_LEVEL)
    logger.setLevel(settings.LOG_LEVEL)
    logger.info("Configuration loaded successfully.")
    logger.info("Environment: %s", settings.ENVIRONMENT.upper())
    logger.info("Starting %s v%s", settings.APP_TITLE, settings.APP_VERSION)

    app = Flask(__name__)

    # =========================================================================================
    #                                       Extensions
    # =========================================================================================

    app.extensions["settings"] = settings
    app.extensions["client"] = HubSpotClient(
        auth=HubSpotAuth(
            base_url=settings.HUBSPOT_BASE_URL,
            api_version=settings.HUBSPOT_API_VERSION,
            access_token=settings.HUBSPOT_ACCESS_TOKEN.get_secret_value(),
            portal_id=settings.HUBSPOT_PORTAL_ID,
        ),
        page_size=settings.HUBSPOT_PAGE_SIZE,
        include_associations=settings.HUBSPOT_INCLUDE_ASSOCIATIONS,
    )
    app.extensions["client"].validate_auth()

    engine = create_db_engine(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        name=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD.get_secret_value(),
        schema=settings.DB_SCHEMA,
    )
    Base.metadata.create_all(engine)
    app.extensions["scans"] = ScanRepository(create_session_factory(engine))

    app.extensions["extraction_service"] = ExtractionService(
        normalizer=NormalizationService(),
        minio=MinioClient(
            enabled=settings.MINIO_ENABLED,
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY.get_secret_value(),
            secret_key=settings.MINIO_SECRET_KEY.get_secret_value(),
            secure=settings.MINIO_SECURE,
            bucket=settings.MINIO_BUCKET,
        ),
        kafka=KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        ),
        pii=PIIService(
            enabled=settings.PII_MASKING_ENABLED,
            hmac_key=settings.PII_HMAC_KEY.get_secret_value(),
        ),
        clickhouse=ClickHouseClient(
            enabled=settings.CLICKHOUSE_ENABLED,
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD.get_secret_value(),
            database=settings.CLICKHOUSE_DATABASE,
        ),
        client=app.extensions["client"],
        scans=app.extensions["scans"],
        environment=settings.ENVIRONMENT,
    )

    # =========================================================================================
    #                                         Routes
    # =========================================================================================

    api = Api(app, title=settings.APP_TITLE, version=settings.APP_VERSION)
    api.add_namespace(health_ns, path="/api/health")
    api.add_namespace(scan_ns, path="/api/scan")
    api.add_namespace(objects_ns, path="/api/objects")
    api.add_namespace(key_ns, path="/api/key")
    api.add_namespace(batch_ns, path="/api/batch")
    api.add_namespace(maintenance_ns, path="/api/maintenance")

    return app


def main():
    settings = validate_settings()
    app = create_app(settings)
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.FLASK_DEBUG)


if __name__ == "__main__":
    main()
