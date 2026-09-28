from datetime import UTC, datetime, timedelta


class TestCleanup:
    def test_deletes_scans_older_than_default_days(self, app, client, scan_repo):
        scan_repo.create("old", "org1", config={})
        scan_repo.update_status("old", "completed")
        with scan_repo._session_factory() as session:
            from app.models.scan import Scan

            row = session.get(Scan, "old")
            row.started_at = datetime.now(UTC) - timedelta(days=60)
            session.commit()

        resp = client.post("/api/maintenance/cleanup")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["deleted_count"] == 1
        assert body["older_than_days"] == 30

    def test_respects_older_than_days_query_param(self, app, client, scan_repo):
        scan_repo.create("recent", "org1", config={})
        scan_repo.update_status("recent", "completed")

        resp = client.post("/api/maintenance/cleanup?older_than_days=1")

        assert resp.status_code == 200
        assert resp.get_json()["older_than_days"] == 1
        assert resp.get_json()["deleted_count"] == 0

    def test_does_not_delete_in_progress_scans_regardless_of_age(
        self, app, client, scan_repo
    ):
        scan_repo.create("running", "org1", config={})
        scan_repo.update_status("running", "in_progress")
        with scan_repo._session_factory() as session:
            from app.models.scan import Scan

            row = session.get(Scan, "running")
            row.started_at = datetime.now(UTC) - timedelta(days=365)
            session.commit()

        resp = client.post("/api/maintenance/cleanup")

        assert resp.get_json()["deleted_count"] == 0
