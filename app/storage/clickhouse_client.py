import json

import clickhouse_connect

from app.logger import logger


class ClickHouseClientError(ValueError):
    """Raised when a ClickHouse operation fails."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class ClickHouseClient:
    """Client for loading extracted HubSpot records into ClickHouse.

    Entirely inert when constructed with `enabled=False` - no connection
    is attempted, and every method becomes a no-op. One table per HubSpot
    object type, auto-created on first insert if missing, with columns
    matching whatever `properties` happen to be present in the records
    being inserted (no fixed, pre-defined schema).
    """

    def __init__(
        self,
        enabled: bool,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        """Initializes the ClickHouse client.

        Args:
            enabled: Whether ClickHouse loading is enabled. When False,
                no connection is made and every method becomes a no-op.
            host: ClickHouse server host.
            port: ClickHouse HTTP interface port.
            user: ClickHouse user.
            password: ClickHouse password.
            database: Target database. Must already exist.
        """
        self._enabled = enabled

        if not self._enabled:
            self._client = None
            return

        self._client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            database=database,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def ping(self) -> bool:
        """Checks whether ClickHouse is reachable.

        Always returns False when the client is disabled. Never raises -
        failures are logged and reported as False, matching
        `MinioClient.ping()`/`HubSpotClient.ping()`.

        Returns:
            True if ClickHouse is reachable; False otherwise.
        """
        if not self.enabled:
            return False
        assert self._client is not None
        try:
            return self._client.ping()
        except Exception as e:
            logger.warning(f"ClickHouse ping failed: {e}")
            return False

    def insert_records(self, object_type: str, records: list[dict]) -> int:
        """Inserts a page of records into the table for `object_type`.

        Flattens each record the same way `NormalizationService.to_parquet`
        does (`id` + top-level `properties`), and creates the target
        table on first use if it doesn't already exist, with columns
        inferred from the flattened records' keys.

        Args:
            object_type: HubSpot object type - used as the table name.
            records: Records to insert, as returned by
                `HubSpotClient.iter_objects`.

        Returns:
            The number of records inserted. 0 if ClickHouse is disabled
            or `records` is empty.

        Raises:
            ClickHouseClientError: If the insert fails.
        """
        if not self.enabled or not records:
            return 0
        assert self._client is not None

        flattened = [
            {
                "id": record.get("id"),
                **record.get("properties", {}),
                "associations": (
                    json.dumps(record["associations"])
                    if record.get("associations")
                    else ""
                ),
            }
            for record in records
        ]

        table = object_type
        columns = list({key for row in flattened for key in row})

        try:
            self._ensure_table(table, columns)
            data = [[str(row.get(col, "")) for col in columns] for row in flattened]
            self._client.insert(table, data, column_names=columns)
        except Exception as e:
            raise ClickHouseClientError(
                f"Failed to insert {len(records)} record(s) into '{table}': {e}"
            )

        return len(flattened)

    def _ensure_table(self, table: str, columns: list[str]) -> None:
        """Creates a table if it doesn't already exist, and adds any of
        `columns` it's missing.

        All columns are created as String - HubSpot property values
        arrive as strings from the API in practice, and this avoids
        needing to infer/reconcile types across records that may have
        differently-shaped properties.

        Different pages (or different records within the same page) can
        have different sets of properties, so this doesn't assume the
        table's shape was already settled by an earlier page - `id` is
        the only column guaranteed to exist on first creation (needed
        for `ORDER BY id`), and any other column is added on demand,
        idempotently, whichever page first introduces it.

        Args:
            table: Table name.
            columns: Column names that must exist on the table.
        """
        assert self._client is not None
        self._client.command(
            f"CREATE TABLE IF NOT EXISTS `{table}` (`id` String) "
            f"ENGINE = MergeTree() ORDER BY id"
        )
        for col in columns:
            if col == "id":
                continue
            self._client.command(
                f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `{col}` String"
            )
