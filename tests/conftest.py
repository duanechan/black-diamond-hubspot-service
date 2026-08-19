from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_restx import Api
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clients.hubspot_client import HubSpotClient
from app.models.base import Base
from app.repositories.scan_repository import ScanRepository
from app.routes.batch import batch_ns
from app.routes.health import health_ns
from app.routes.key import key_ns
from app.routes.maintenance import maintenance_ns
from app.routes.objects import objects_ns
from app.routes.scan import scan_ns
from app.services.extraction_service import ExtractionService


@pytest.fixture
def scan_repo():
    """A ScanRepository backed by a real in-memory SQLite database.

    Uses the actual ORM/session code path (not a hand-rolled fake), so
    tests exercise the real merge semantics of `update_object_progress`
    (whole-entry replacement of progress[object_type], not a deep merge).

    StaticPool + check_same_thread=False: extraction runs in a
    background thread, which opens its own session/connection - without
    this, that thread would get a fresh, separate in-memory database
    (SQLite ":memory:" is per-connection) instead of sharing the one
    the test set up.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return ScanRepository(sessionmaker(bind=engine))


@pytest.fixture
def app(scan_repo):
    """A Flask app with every route namespace registered, and
    app.extensions populated with a real scan_repo plus mocked
    settings/client/extraction_service.

    HMAC auth is disabled by default (settings.HMAC_ENABLED = False) so
    route tests can focus on route logic rather than request signing;
    tests that specifically cover HMAC behavior enable it explicitly.
    """
    flask_app = Flask(__name__)
    api = Api(flask_app)
    api.add_namespace(health_ns, path="/api/health")
    api.add_namespace(scan_ns, path="/api/scan")
    api.add_namespace(objects_ns, path="/api/objects")
    api.add_namespace(key_ns, path="/api/key")
    api.add_namespace(batch_ns, path="/api/batch")
    api.add_namespace(maintenance_ns, path="/api/maintenance")

    flask_app.extensions["settings"] = MagicMock(
        HMAC_ENABLED=False,
        APP_TITLE="hubspot-service",
        APP_VERSION="1.0",
        MINIO_BUCKET="test-bucket",
        HUBSPOT_INCLUDE_ASSOCIATIONS=True,
        CLEANUP_DAYS=30,
    )
    flask_app.extensions["scans"] = scan_repo
    flask_app.extensions["client"] = MagicMock(spec=HubSpotClient)
    flask_app.extensions["extraction_service"] = MagicMock(spec=ExtractionService)
    flask_app.extensions["minio"] = MagicMock()
    flask_app.extensions["kafka"] = MagicMock()
    flask_app.extensions["clickhouse"] = MagicMock()

    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
