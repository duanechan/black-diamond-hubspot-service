from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_restx import Api

from app.routes.health import health_ns


@pytest.fixture
def app_with_health(request):
    """A minimal Flask app with only the health namespace registered, and
    app.extensions populated with mocked clients whose ping() results are
    controlled per-test via the `pings` param.
    """
    pings = getattr(request, "param", {})
    defaults = {"client": True, "minio": True, "kafka": True, "clickhouse": True}
    pings = {**defaults, **pings}

    app = Flask(__name__)
    Api(app).add_namespace(health_ns, path="/api/health")

    app.extensions["settings"] = MagicMock(
        APP_TITLE="hubspot-service", APP_VERSION="1.0"
    )
    app.extensions["client"] = MagicMock(ping=lambda: pings["client"])
    app.extensions["minio"] = MagicMock(ping=lambda: pings["minio"])
    app.extensions["kafka"] = MagicMock(ping=lambda: pings["kafka"])
    app.extensions["clickhouse"] = MagicMock(ping=lambda: pings["clickhouse"])

    return app


class TestHealth:
    def test_all_reachable_is_healthy_200(self, app_with_health):
        with app_with_health.test_client() as c:
            resp = c.get("/api/health/")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "healthy"
        assert body["hubspot_connected"] is True
        assert body["minio_connected"] is True
        assert body["kafka_connected"] is True
        assert body["clickhouse_connected"] is True

    @pytest.mark.parametrize(
        "app_with_health",
        [
            {"client": False},
            {"minio": False},
            {"kafka": False},
            {"clickhouse": False},
        ],
        indirect=True,
    )
    def test_any_dependency_down_is_degraded_503(self, app_with_health):
        with app_with_health.test_client() as c:
            resp = c.get("/api/health/")

        assert resp.status_code == 503
        assert resp.get_json()["status"] == "degraded"

    def test_response_includes_service_metadata(self, app_with_health):
        with app_with_health.test_client() as c:
            body = c.get("/api/health/").get_json()

        assert body["service"] == "hubspot-service"
        assert body["version"] == "1.0"
