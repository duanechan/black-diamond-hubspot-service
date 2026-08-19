from unittest.mock import MagicMock, patch

import pytest

from app.storage.clickhouse_client import ClickHouseClient, ClickHouseClientError


@pytest.fixture
def mock_ch_client():
    """A MagicMock standing in for the clickhouse_connect client instance."""
    return MagicMock()


@pytest.fixture
def make_client(mock_ch_client):
    """Builds a ClickHouseClient with clickhouse_connect.get_client patched
    to return `mock_ch_client`, so no real connection is attempted."""

    def _make(enabled: bool = True) -> ClickHouseClient:
        with patch(
            "app.storage.clickhouse_client.clickhouse_connect.get_client",
            return_value=mock_ch_client,
        ) as get_client:
            client = ClickHouseClient(
                enabled=enabled,
                host="localhost",
                port=8123,
                user="default",
                password="default",
                database="hubspot",
            )
        if enabled:
            get_client.assert_called_once_with(
                host="localhost",
                port=8123,
                username="default",
                password="default",
                database="hubspot",
            )
        else:
            get_client.assert_not_called()
        return client

    return _make


class TestDisabled:
    def test_ping_returns_false_without_connecting(self, make_client, mock_ch_client):
        client = make_client(enabled=False)
        assert client.ping() is False
        mock_ch_client.ping.assert_not_called()

    def test_insert_records_is_a_noop(self, make_client, mock_ch_client):
        client = make_client(enabled=False)
        result = client.insert_records("contacts", [{"id": "1", "properties": {}}])
        assert result == 0
        mock_ch_client.command.assert_not_called()
        mock_ch_client.insert.assert_not_called()


class TestPing:
    def test_ping_true_when_reachable(self, make_client, mock_ch_client):
        mock_ch_client.ping.return_value = True
        assert make_client().ping() is True

    def test_ping_false_on_exception(self, make_client, mock_ch_client):
        mock_ch_client.ping.side_effect = Exception("connection refused")
        assert make_client().ping() is False


class TestInsertRecords:
    def test_empty_records_is_a_noop(self, make_client, mock_ch_client):
        client = make_client()
        assert client.insert_records("contacts", []) == 0
        mock_ch_client.command.assert_not_called()

    def test_happy_path_creates_table_and_inserts(self, make_client, mock_ch_client):
        client = make_client()
        records = [
            {"id": "1", "properties": {"email": "a@x.com"}},
            {"id": "2", "properties": {"email": "b@x.com"}},
        ]

        count = client.insert_records("contacts", records)

        assert count == 2
        create_call = mock_ch_client.command.call_args_list[0].args[0]
        assert "CREATE TABLE IF NOT EXISTS `contacts`" in create_call
        assert "ORDER BY id" in create_call

        insert_args, insert_kwargs = mock_ch_client.insert.call_args
        assert insert_args[0] == "contacts"
        assert set(insert_kwargs["column_names"]) == {"id", "email", "associations"}

    def test_schema_drift_adds_missing_column_on_later_page(
        self, make_client, mock_ch_client
    ):
        """A property absent from earlier pages but present on a later one
        must be added to the table, not silently dropped or fail the insert.
        """
        client = make_client()

        client.insert_records(
            "contacts", [{"id": "1", "properties": {"email": "a@x.com"}}]
        )
        client.insert_records(
            "contacts",
            [{"id": "2", "properties": {"email": "b@x.com", "phone": "555"}}],
        )

        alter_commands = [
            call.args[0]
            for call in mock_ch_client.command.call_args_list
            if "ALTER TABLE" in call.args[0]
        ]
        assert any("`phone`" in cmd for cmd in alter_commands)

    def test_schema_drift_within_a_single_page(self, make_client, mock_ch_client):
        """Column set must be the union of every record in the page, not
        just the first record's keys."""
        client = make_client()
        records = [
            {"id": "1", "properties": {"email": "a@x.com"}},
            {"id": "2", "properties": {"email": "b@x.com", "phone": "555"}},
        ]

        client.insert_records("contacts", records)

        _, insert_kwargs = mock_ch_client.insert.call_args
        assert set(insert_kwargs["column_names"]) == {
            "id",
            "email",
            "phone",
            "associations",
        }

    def test_associations_are_preserved_as_json(self, make_client, mock_ch_client):
        client = make_client()
        records = [
            {
                "id": "1",
                "properties": {"email": "a@x.com"},
                "associations": {"companies": ["55", "56"]},
            }
        ]

        client.insert_records("contacts", records)

        _, insert_kwargs = mock_ch_client.insert.call_args
        row = mock_ch_client.insert.call_args.args[1][0]
        associations_index = insert_kwargs["column_names"].index("associations")
        assert row[associations_index] == '{"companies": ["55", "56"]}'

    def test_raises_clickhouse_client_error_on_failure(
        self, make_client, mock_ch_client
    ):
        mock_ch_client.insert.side_effect = Exception("boom")
        client = make_client()

        with pytest.raises(ClickHouseClientError):
            client.insert_records("contacts", [{"id": "1", "properties": {}}])
