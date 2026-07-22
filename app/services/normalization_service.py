from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq


class NormalizationService:
    """Converts extracted HubSpot records into storable output formats."""

    def to_json(self, records: list[dict]) -> bytes:
        """Convert records to JSON.

        Args:
            records: Records to serialize.

        Returns:
            The serialized JSON data, UTF-8 encoded.
        """
        import json
        from datetime import date, datetime

        def _default(value):
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            raise TypeError(
                f"Object of type {type(value).__name__} is not JSON serializable"
            )

        return json.dumps(records, default=_default).encode("utf-8")

    def to_parquet(self, records: list[dict]) -> bytes:
        """Convert records to Apache Parquet format.

        Each record's `properties` dict is flattened into top-level
        columns (e.g. `properties.email` becomes column `email`) so the
        resulting schema is flat and directly queryable, rather than
        nesting every HubSpot property under one struct column.

        Args:
            records: Records to serialize, as returned by
                `HubSpotClient.iter_objects` (each with `id`, `properties`,
                and optionally `associations`/timestamps).

        Returns:
            The serialized Parquet data.

        Raises:
            ValueError: If the records cannot be converted to Parquet.
        """
        try:
            flattened = [
                {
                    "id": record.get("id"),
                    **record.get("properties", {}),
                }
                for record in records
            ]
            buffer = BytesIO()
            pq.write_table(table=pa.Table.from_pylist(flattened), where=buffer)
            return buffer.getvalue()
        except pa.ArrowException as e:
            raise ValueError(f"Failed to convert records to parquet: {e}")

    def deduplicate(self, records: list[dict]) -> list[dict]:
        """Remove duplicate records by HubSpot record ID.

        When duplicate IDs are present, the last occurrence is retained.

        Args:
            records: Records to deduplicate.

        Returns:
            A list containing unique records.
        """
        return list({record["id"]: record for record in records}.values())
