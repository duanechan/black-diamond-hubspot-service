class TestKeyVerify:
    def test_returns_valid_when_hmac_disabled(self, client):
        resp = client.get("/api/key/verify")

        assert resp.status_code == 200
        assert resp.get_json() == {"valid": True, "message": "HMAC key verified"}
