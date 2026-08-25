import uuid


class TestClickHouseIntegration:
    def test_ping_returns_true_when_reachable(self, real_clickhouse_client):
        assert real_clickhouse_client.ping() is True

    def test_insert_and_query_round_trip(self, real_clickhouse_client):
        table = f"test_contacts_{uuid.uuid4().hex[:8]}"
        try:
            count = real_clickhouse_client.insert_records(
                table,
                [
                    {"id": "1", "properties": {"email": "a@x.com"}},
                    {"id": "2", "properties": {"email": "b@x.com"}},
                ],
            )
            assert count == 2

            result = real_clickhouse_client._client.query(
                f"SELECT id, email FROM `{table}` ORDER BY id"
            )
            assert result.result_rows == [("1", "a@x.com"), ("2", "b@x.com")]
        finally:
            real_clickhouse_client._client.command(f"DROP TABLE IF EXISTS `{table}`")

    def test_schema_drift_across_real_alter_table(self, real_clickhouse_client):
        """The exact scenario that was previously only ever verified
        against a mock: a later page introduces a column the table
        wasn't originally created with, and ALTER TABLE ADD COLUMN must
        actually succeed against a real ClickHouse server."""
        table = f"test_drift_{uuid.uuid4().hex[:8]}"
        try:
            real_clickhouse_client.insert_records(
                table, [{"id": "1", "properties": {"email": "a@x.com"}}]
            )
            # Second page introduces "phone", absent from the first page.
            real_clickhouse_client.insert_records(
                table,
                [{"id": "2", "properties": {"email": "b@x.com", "phone": "555"}}],
            )

            result = real_clickhouse_client._client.query(
                f"SELECT id, email, phone FROM `{table}` ORDER BY id"
            )
            assert result.result_rows == [
                ("1", "a@x.com", ""),
                ("2", "b@x.com", "555"),
            ]
        finally:
            real_clickhouse_client._client.command(f"DROP TABLE IF EXISTS `{table}`")

    def test_associations_preserved_as_json_string(self, real_clickhouse_client):
        table = f"test_assoc_{uuid.uuid4().hex[:8]}"
        try:
            real_clickhouse_client.insert_records(
                table,
                [
                    {
                        "id": "1",
                        "properties": {"email": "a@x.com"},
                        "associations": {"companies": ["55", "56"]},
                    }
                ],
            )

            result = real_clickhouse_client._client.query(
                f"SELECT associations FROM `{table}` WHERE id = '1'"
            )
            assert result.result_rows[0][0] == '{"companies": ["55", "56"]}'
        finally:
            real_clickhouse_client._client.command(f"DROP TABLE IF EXISTS `{table}`")
