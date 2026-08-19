from datetime import UTC, datetime, timedelta

import pytest

from app.models.scan import Scan
from app.repositories.scan_repository import ScanNotFoundError


def backdate(scan_repo, scan_id: str, days: int) -> None:
    with scan_repo._session_factory() as session:
        row = session.get(Scan, scan_id)
        row.started_at = datetime.now(UTC) - timedelta(days=days)
        session.commit()


class TestCreate:
    def test_creates_scan_in_started_state(self, scan_repo):
        scan = scan_repo.create("s1", "org1", config={"object_types": ["contacts"]})

        assert scan.scan_id == "s1"
        assert scan.org_id == "org1"
        assert scan.status == "started"
        assert scan.progress == {}
        assert scan.config == {"object_types": ["contacts"]}

    def test_persisted_and_retrievable(self, scan_repo):
        scan_repo.create("s1", "org1", config={})

        fetched = scan_repo.get("s1")

        assert fetched.scan_id == "s1"


class TestGet:
    def test_raises_for_missing_scan(self, scan_repo):
        with pytest.raises(ScanNotFoundError):
            scan_repo.get("nonexistent")


class TestUpdateObjectProgress:
    def test_sets_progress_for_object_type(self, scan_repo):
        scan_repo.create("s1", "org1", config={})

        scan_repo.update_object_progress(
            "s1", "contacts", {"status": "complete", "records_extracted": 10}
        )

        scan = scan_repo.get("s1")
        assert scan.progress["contacts"] == {
            "status": "complete",
            "records_extracted": 10,
        }

    def test_does_not_touch_other_object_types(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})

        scan_repo.update_object_progress("s1", "companies", {"status": "failed"})

        scan = scan_repo.get("s1")
        assert scan.progress["contacts"] == {"status": "complete"}
        assert scan.progress["companies"] == {"status": "failed"}

    def test_entry_fully_replaces_prior_entry_not_deep_merged(self, scan_repo):
        """update_object_progress replaces the whole entry for that
        object type - it does not merge individual keys within it."""
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress(
            "s1", "contacts", {"status": "in_progress", "records_extracted": 5}
        )

        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})

        scan = scan_repo.get("s1")
        assert scan.progress["contacts"] == {"status": "complete"}
        assert "records_extracted" not in scan.progress["contacts"]

    def test_bumps_updated_at(self, scan_repo):
        scan = scan_repo.create("s1", "org1", config={})
        original_updated_at = scan.updated_at

        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})

        assert scan_repo.get("s1").updated_at >= original_updated_at

    def test_raises_for_missing_scan(self, scan_repo):
        with pytest.raises(ScanNotFoundError):
            scan_repo.update_object_progress("nonexistent", "contacts", {})


class TestUpdateStatus:
    def test_updates_status(self, scan_repo):
        scan_repo.create("s1", "org1", config={})

        scan_repo.update_status("s1", "completed")

        assert scan_repo.get("s1").status == "completed"

    def test_raises_for_missing_scan(self, scan_repo):
        with pytest.raises(ScanNotFoundError):
            scan_repo.update_status("nonexistent", "completed")


class TestList:
    def test_no_filter_returns_all(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.create("s2", "org2", config={})

        assert {s.scan_id for s in scan_repo.list()} == {"s1", "s2"}

    def test_filters_by_org_id(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.create("s2", "org2", config={})

        result = scan_repo.list(org_id="org1")

        assert [s.scan_id for s in result] == ["s1"]

    def test_filters_by_status(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.create("s2", "org1", config={})
        scan_repo.update_status("s2", "completed")

        result = scan_repo.list(status="completed")

        assert [s.scan_id for s in result] == ["s2"]

    def test_filters_by_org_id_and_status_together(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.create("s2", "org2", config={})
        scan_repo.update_status("s1", "completed")
        scan_repo.update_status("s2", "completed")

        result = scan_repo.list(org_id="org1", status="completed")

        assert [s.scan_id for s in result] == ["s1"]


class TestDelete:
    def test_removes_scan(self, scan_repo):
        scan_repo.create("s1", "org1", config={})

        scan_repo.delete("s1")

        with pytest.raises(ScanNotFoundError):
            scan_repo.get("s1")

    def test_raises_for_missing_scan(self, scan_repo):
        with pytest.raises(ScanNotFoundError):
            scan_repo.delete("nonexistent")


class TestDeleteOlderThan:
    def test_deletes_terminal_scans_older_than_cutoff(self, scan_repo):
        scan_repo.create("old", "org1", config={})
        scan_repo.update_status("old", "completed")
        backdate(scan_repo, "old", days=60)

        count = scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        assert count == 1
        with pytest.raises(ScanNotFoundError):
            scan_repo.get("old")

    def test_does_not_delete_scans_within_cutoff(self, scan_repo):
        scan_repo.create("recent", "org1", config={})
        scan_repo.update_status("recent", "completed")

        count = scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        assert count == 0
        assert scan_repo.get("recent") is not None

    def test_does_not_delete_in_progress_scans_regardless_of_age(self, scan_repo):
        scan_repo.create("running", "org1", config={})
        scan_repo.update_status("running", "in_progress")
        backdate(scan_repo, "running", days=365)

        count = scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        assert count == 0
        assert scan_repo.get("running") is not None

    def test_does_not_delete_started_scans_regardless_of_age(self, scan_repo):
        scan_repo.create("just_started", "org1", config={})
        backdate(scan_repo, "just_started", days=365)

        count = scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        assert count == 0

    def test_deletes_failed_and_cancelled_too(self, scan_repo):
        scan_repo.create("f", "org1", config={})
        scan_repo.update_status("f", "failed")
        backdate(scan_repo, "f", days=60)
        scan_repo.create("c", "org1", config={})
        scan_repo.update_status("c", "cancelled")
        backdate(scan_repo, "c", days=60)

        count = scan_repo.delete_older_than(datetime.now(UTC) - timedelta(days=30))

        assert count == 2
