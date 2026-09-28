from app.constants import SUPPORTED_OBJECTS


class TestObjects:
    def test_returns_all_supported_object_types(self, client):
        resp = client.get("/api/objects/")

        assert resp.status_code == 200
        names = {o["name"] for o in resp.get_json()["supported_objects"]}
        assert names == set(SUPPORTED_OBJECTS.keys())

    def test_each_entry_includes_its_config(self, client):
        resp = client.get("/api/objects/")

        by_name = {o["name"]: o for o in resp.get_json()["supported_objects"]}
        assert by_name["contacts"]["api_endpoint"] == "/crm/v3/objects/contacts"
        assert by_name["owners"]["default_properties"] == []
        assert by_name["engagements"]["supports_associations"] is True
