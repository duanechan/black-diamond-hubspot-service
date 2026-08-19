import json
from datetime import UTC, date, datetime
from io import BytesIO

import pyarrow.parquet as pq
import pytest

from app.services.normalization_service import NormalizationService


class TestToJson:
    def test_round_trips_simple_records(self):
        records = [{"id": "1", "properties": {"email": "a@x.com"}}]

        result = NormalizationService().to_json(records)

        assert json.loads(result) == records

    def test_returns_utf8_encoded_bytes(self):
        result = NormalizationService().to_json([{"id": "1"}])

        assert isinstance(result, bytes)

    def test_serializes_datetime_as_isoformat(self):
        dt = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)
        records = [{"id": "1", "extracted_at": dt}]

        result = json.loads(NormalizationService().to_json(records))

        assert result[0]["extracted_at"] == dt.isoformat()

    def test_serializes_date_as_isoformat(self):
        d = date(2026, 1, 15)
        records = [{"id": "1", "day": d}]

        result = json.loads(NormalizationService().to_json(records))

        assert result[0]["day"] == d.isoformat()

    def test_preserves_associations_unflattened(self):
        """Unlike to_parquet, to_json doesn't flatten - associations
        should come through as a nested dict, not a JSON string."""
        records = [
            {
                "id": "1",
                "properties": {"email": "a@x.com"},
                "associations": {"companies": ["55"]},
            }
        ]

        result = json.loads(NormalizationService().to_json(records))

        assert result[0]["associations"] == {"companies": ["55"]}

    def test_empty_records_list(self):
        result = NormalizationService().to_json([])

        assert json.loads(result) == []

    def test_non_serializable_type_raises(self):
        class Unserializable:
            pass

        with pytest.raises(TypeError):
            NormalizationService().to_json([{"id": "1", "bad": Unserializable()}])


class TestDeduplicate:
    def test_removes_duplicate_ids_keeping_last(self):
        records = [
            {"id": "1", "properties": {"email": "old@x.com"}},
            {"id": "2", "properties": {"email": "b@x.com"}},
            {"id": "1", "properties": {"email": "new@x.com"}},
        ]

        result = NormalizationService().deduplicate(records)

        by_id = {r["id"]: r for r in result}
        assert len(result) == 2
        assert by_id["1"]["properties"]["email"] == "new@x.com"

    def test_no_duplicates_returns_all(self):
        records = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        result = NormalizationService().deduplicate(records)

        assert len(result) == 3

    def test_empty_list(self):
        assert NormalizationService().deduplicate([]) == []


class TestToParquet:
    def test_flattens_properties_to_top_level_columns(self):
        records = [{"id": "1", "properties": {"email": "a@x.com"}}]

        table = pq.read_table(BytesIO(NormalizationService().to_parquet(records)))

        assert table.to_pylist() == [
            {"id": "1", "email": "a@x.com", "associations": None}
        ]

    def test_associations_are_preserved_as_json_string(self):
        records = [
            {
                "id": "1",
                "properties": {"email": "a@x.com"},
                "associations": {"companies": ["55", "56"]},
            }
        ]

        table = pq.read_table(BytesIO(NormalizationService().to_parquet(records)))

        row = table.to_pylist()[0]
        assert row["associations"] == '{"companies": ["55", "56"]}'

    def test_missing_associations_is_null_not_dropped(self):
        records = [{"id": "1", "properties": {"email": "a@x.com"}}]

        table = pq.read_table(BytesIO(NormalizationService().to_parquet(records)))

        assert "associations" in table.column_names
        assert table.to_pylist()[0]["associations"] is None
