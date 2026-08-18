import hashlib
import hmac
import time
from unittest.mock import MagicMock

from flask import Flask

from app.auth.hmac_auth import require_hmac

CORE_SECRET = "core-secret-key"
ENGINEER_SECRET = "engineer-secret-key"


def make_app(hmac_enabled: bool = True, max_age: int = 300):
    app = Flask(__name__)

    settings = MagicMock()
    settings.HMAC_ENABLED = hmac_enabled
    settings.HMAC_SIGNATURE_MAX_AGE = max_age
    settings.HMAC_SECRET_KEY_CORE = MagicMock(get_secret_value=lambda: CORE_SECRET)
    settings.HMAC_SECRET_KEY_ENGINEER = MagicMock(
        get_secret_value=lambda: ENGINEER_SECRET
    )
    app.extensions["settings"] = settings

    @app.route("/protected", methods=["GET", "POST"])
    @require_hmac()
    def protected():
        return {"ok": True}, 200

    @app.route("/engineer-only", methods=["GET"])
    @require_hmac(requires_engineer_key=True)
    def engineer_only():
        return {"ok": True}, 200

    return app


def sign(method: str, path: str, timestamp: str, body: str, secret: str) -> str:
    message = f"{method}\n{path}\n{timestamp}\n{body}"
    return hmac.new(
        key=secret.encode(), msg=message.encode(), digestmod=hashlib.sha256
    ).hexdigest()


class TestBypass:
    def test_hmac_disabled_skips_all_checks(self):
        app = make_app(hmac_enabled=False)
        with app.test_client() as c:
            resp = c.get("/protected")

        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}


class TestMissingOrInvalidHeaders:
    def test_missing_both_headers_returns_401(self):
        app = make_app()
        with app.test_client() as c:
            resp = c.get("/protected")

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_HEADERS"

    def test_missing_signature_only_returns_401(self):
        app = make_app()
        with app.test_client() as c:
            resp = c.get("/protected", headers={"X-Timestamp": str(int(time.time()))})

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_HEADERS"

    def test_non_numeric_timestamp_returns_401(self):
        app = make_app()
        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": "not-a-number", "X-Signature": "whatever"},
            )

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_HEADERS"


class TestTimestampFreshness:
    def test_timestamp_too_old_returns_401(self):
        app = make_app(max_age=300)
        old_timestamp = str(int(time.time()) - 600)
        signature = sign("GET", "/protected", old_timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": old_timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "AUTH_ERR"

    def test_timestamp_within_window_is_accepted(self):
        app = make_app(max_age=300)
        timestamp = str(int(time.time()))
        signature = sign("GET", "/protected", timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 200


class TestSignatureValidation:
    def test_wrong_signature_returns_401(self):
        app = make_app()
        timestamp = str(int(time.time()))

        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": timestamp, "X-Signature": "totally-wrong"},
            )

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "AUTH_ERR"

    def test_correct_signature_on_get_is_accepted(self):
        app = make_app()
        timestamp = str(int(time.time()))
        signature = sign("GET", "/protected", timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

    def test_correct_signature_on_post_includes_body(self):
        app = make_app()
        timestamp = str(int(time.time()))
        body = '{"scan_id": "abc"}'
        signature = sign("POST", "/protected", timestamp, body, CORE_SECRET)

        with app.test_client() as c:
            resp = c.post(
                "/protected",
                data=body,
                content_type="application/json",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 200

    def test_signature_computed_over_wrong_body_is_rejected(self):
        """The signature must cover the actual body sent - signing one
        body and sending another must fail."""
        app = make_app()
        timestamp = str(int(time.time()))
        signature = sign("POST", "/protected", timestamp, '{"a": 1}', CORE_SECRET)

        with app.test_client() as c:
            resp = c.post(
                "/protected",
                data='{"a": 2}',
                content_type="application/json",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 401

    def test_query_string_is_included_in_signed_path(self):
        app = make_app()
        timestamp = str(int(time.time()))
        # Signature computed WITHOUT the query string that will actually
        # be sent - should be rejected since full_path is part of the message.
        signature = sign("GET", "/protected", timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected?org_id=org1",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 401

    def test_query_string_correctly_signed_is_accepted(self):
        app = make_app()
        timestamp = str(int(time.time()))
        signature = sign("GET", "/protected?org_id=org1", timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected?org_id=org1",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 200


class TestEngineerKey:
    def test_core_signature_rejected_on_engineer_route(self):
        app = make_app()
        timestamp = str(int(time.time()))
        # Signed with the CORE secret, but the route requires the
        # ENGINEER secret.
        signature = sign("GET", "/engineer-only", timestamp, "", CORE_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/engineer-only",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 401

    def test_engineer_signature_accepted_on_engineer_route(self):
        app = make_app()
        timestamp = str(int(time.time()))
        signature = sign("GET", "/engineer-only", timestamp, "", ENGINEER_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/engineer-only",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 200

    def test_engineer_signature_rejected_on_core_route(self):
        app = make_app()
        timestamp = str(int(time.time()))
        signature = sign("GET", "/protected", timestamp, "", ENGINEER_SECRET)

        with app.test_client() as c:
            resp = c.get(
                "/protected",
                headers={"X-Timestamp": timestamp, "X-Signature": signature},
            )

        assert resp.status_code == 401
