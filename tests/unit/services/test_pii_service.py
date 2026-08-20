import hashlib
import hmac

from app.services.pii_service import PIIService


def expected_hash(value, key: str) -> str:
    return hmac.new(
        key=key.encode(), msg=str(value).encode(), digestmod=hashlib.sha256
    ).hexdigest()


class TestDisabled:
    def test_records_returned_unchanged(self):
        svc = PIIService(enabled=False, hmac_key="secret")
        records = [{"id": "1", "properties": {"email": "a@x.com", "firstname": "A"}}]

        result = svc.mask(records)

        assert result[0]["properties"]["email"] == "a@x.com"
        assert result[0]["properties"]["firstname"] == "A"

    def test_enabled_property_reflects_constructor_arg(self):
        assert PIIService(enabled=False, hmac_key="k").enabled is False
        assert PIIService(enabled=True, hmac_key="k").enabled is True


class TestMaskingLowercaseFields:
    def test_masks_email_firstname_lastname_phone(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {
            "id": "1",
            "properties": {
                "email": "a@x.com",
                "firstname": "Alice",
                "lastname": "Smith",
                "phone": "555-1234",
            },
        }

        svc.mask([record])

        props = record["properties"]
        assert props["email"] == expected_hash("a@x.com", "secret")
        assert props["firstname"] == expected_hash("Alice", "secret")
        assert props["lastname"] == expected_hash("Smith", "secret")
        assert props["phone"] == expected_hash("555-1234", "secret")


class TestMaskingCamelCaseFields:
    def test_masks_firstName_lastName(self):
        """These are what owners/engagements use, per their reshaping in
        HubSpotClient.iter_owners/iter_engagements."""
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {
            "id": "1",
            "properties": {
                "email": "a@x.com",
                "firstName": "Alice",
                "lastName": "Smith",
            },
        }

        svc.mask([record])

        props = record["properties"]
        assert props["firstName"] == expected_hash("Alice", "secret")
        assert props["lastName"] == expected_hash("Smith", "secret")


class TestNonPiiFieldsUntouched:
    def test_other_properties_left_as_is(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {
            "id": "1",
            "properties": {
                "email": "a@x.com",
                "dealname": "Big Deal",
                "amount": "1000",
            },
        }

        svc.mask([record])

        assert record["properties"]["dealname"] == "Big Deal"
        assert record["properties"]["amount"] == "1000"


class TestDeterminism:
    def test_same_value_same_key_produces_same_hash(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        r1: dict = {"id": "1", "properties": {"email": "a@x.com"}}
        r2: dict = {"id": "2", "properties": {"email": "a@x.com"}}

        svc.mask([r1, r2])

        assert r1["properties"]["email"] == r2["properties"]["email"]

    def test_different_keys_produce_different_hashes(self):
        record_a: dict = {"id": "1", "properties": {"email": "a@x.com"}}
        record_b: dict = {"id": "1", "properties": {"email": "a@x.com"}}

        PIIService(enabled=True, hmac_key="key-one").mask([record_a])
        PIIService(enabled=True, hmac_key="key-two").mask([record_b])

        assert record_a["properties"]["email"] != record_b["properties"]["email"]

    def test_different_values_produce_different_hashes(self):
        record_a: dict = {"id": "1", "properties": {"email": "a@x.com"}}
        record_b: dict = {"id": "2", "properties": {"email": "b@x.com"}}
        svc = PIIService(enabled=True, hmac_key="secret")

        svc.mask([record_a, record_b])

        assert record_a["properties"]["email"] != record_b["properties"]["email"]


class TestEdgeCases:
    def test_none_value_left_as_none_not_hashed(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {"id": "1", "properties": {"email": None}}

        svc.mask([record])

        assert record["properties"]["email"] is None

    def test_missing_properties_key_does_not_crash(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {"id": "1"}

        result = svc.mask([record])

        assert result[0] == {"id": "1"}

    def test_empty_properties_dict_does_not_crash(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {"id": "1", "properties": {}}

        result = svc.mask([record])

        assert result[0]["properties"] == {}

    def test_empty_records_list(self):
        svc = PIIService(enabled=True, hmac_key="secret")

        assert svc.mask([]) == []

    def test_non_string_value_is_stringified_before_hashing(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {"id": "1", "properties": {"phone": 5551234}}

        svc.mask([record])

        assert record["properties"]["phone"] == expected_hash(5551234, "secret")

    def test_multiple_records_all_masked(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        records: list[dict] = [
            {"id": "1", "properties": {"email": "a@x.com"}},
            {"id": "2", "properties": {"email": "b@x.com"}},
            {"id": "3", "properties": {"email": "c@x.com"}},
        ]

        svc.mask(records)

        for r in records:
            assert (
                r["properties"]["email"] != r["id"]
            )  # sanity: got hashed to something
            assert len(r["properties"]["email"]) == 64  # sha256 hex digest length


class TestMutatesInPlace:
    def test_returns_same_list_and_dict_identities(self):
        svc = PIIService(enabled=True, hmac_key="secret")
        record: dict = {"id": "1", "properties": {"email": "a@x.com"}}
        records = [record]

        result = svc.mask(records)

        assert result is records
        assert result[0] is record
