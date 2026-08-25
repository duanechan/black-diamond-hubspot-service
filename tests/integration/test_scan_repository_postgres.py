from datetime import UTC, datetime, timedelta

import pytest

from app.models.scan import Scan
from app.repositories.scan_repository import ScanNotFoundError


class TestScanRepositoryPostgres:
    def test_create_and_get_round_trip(self, real_scan_repo, unique_scan_id):
        real_scan_repo.create(
            unique_scan_id, "org1", config={"object_types": ["contacts"]}
        )
        try:
            scan = real_scan_repo.get(unique_scan_id)
            assert scan.scan_id == unique_scan_id
            assert scan.status == "started"
            assert scan.config == {"object_types": ["contacts"]}
        finally:
            real_scan_repo.delete(unique_scan_id)

    def test_json_column_round_trips_nested_structure(
        self, real_scan_repo, unique_scan_id
    ):
        """Postgres's JSON column must correctly store/retrieve nested
        dicts/lists, not just flat key-value pairs - SQLite's JSON
        handling can't be assumed identical."""
        real_scan_repo.create(unique_scan_id, "org1", config={})
        try:
            real_scan_repo.update_object_progress(
                unique_scan_id,
                "contacts",
                {
                    "status": "in_progress",
                    "records_extracted": 42,
                    "cursor": "abc123",
                    "nested": {"a": [1, 2, 3], "b": None},
                },
            )

            scan = real_scan_repo.get(unique_scan_id)

            assert scan.progress["contacts"]["nested"] == {"a": [1, 2, 3], "b": None}
            assert scan.progress["contacts"]["records_extracted"] == 42
            assert scan.progress["contacts"]["cursor"] == "abc123"
        finally:
            real_scan_repo.delete(unique_scan_id)

    def test_update_object_progress_replaces_whole_entry(
        self, real_scan_repo, unique_scan_id
    ):
        real_scan_repo.create(unique_scan_id, "org1", config={})
        try:
            real_scan_repo.update_object_progress(
                unique_scan_id,
                "contacts",
                {"status": "in_progress", "records_extracted": 5},
            )
            real_scan_repo.update_object_progress(
                unique_scan_id, "contacts", {"status": "complete"}
            )

            scan = real_scan_repo.get(unique_scan_id)

            assert scan.progress["contacts"] == {"status": "complete"}
        finally:
            real_scan_repo.delete(unique_scan_id)

    def test_delete_older_than_uses_timezone_aware_comparison(
        self, real_scan_repo, unique_scan_id
    ):
        """Postgres TIMESTAMP columns and Python's timezone-aware
        datetimes must compare correctly - a common source of
        off-by-timezone bugs an in-memory SQLite test wouldn't catch."""
        real_scan_repo.create(unique_scan_id, "org1", config={})
        real_scan_repo.update_status(unique_scan_id, "completed")

        with real_scan_repo._session_factory() as session:
            row = session.get(Scan, unique_scan_id)
            row.started_at = datetime.now(UTC) - timedelta(days=60)
            session.commit()

        real_scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        with pytest.raises(ScanNotFoundError):
            real_scan_repo.get(unique_scan_id)

    def test_delete_older_than_does_not_delete_recent_scan(
        self, real_scan_repo, unique_scan_id
    ):
        real_scan_repo.create(unique_scan_id, "org1", config={})
        real_scan_repo.update_status(unique_scan_id, "completed")
        try:
            real_scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

            assert real_scan_repo.get(unique_scan_id) is not None
        finally:
            real_scan_repo.delete(unique_scan_id)

    def test_get_raises_for_missing_scan(self, real_scan_repo, unique_scan_id):
        with pytest.raises(ScanNotFoundError):
            real_scan_repo.get(unique_scan_id)
