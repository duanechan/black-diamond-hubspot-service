class TestStart:
    def test_missing_required_fields_returns_400(self, client):
        resp = client.post("/api/scan/start", json={})

        assert resp.status_code == 400
        fields = resp.get_json()["fields"]
        assert set(fields.keys()) == {"scan_id", "org_id", "objects"}

    def test_starts_scan_and_persists_it(self, app, client, scan_repo):
        resp = client.post(
            "/api/scan/start",
            json={
                "scan_id": "s1",
                "org_id": "org1",
                "objects": ["contacts", "leads"],
                "destination": {},
            },
        )

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["success"] is True
        assert set(body["extractions"].keys()) == {"contacts", "leads"}

        scan = scan_repo.get("s1")
        assert scan.org_id == "org1"
        assert scan.config["object_types"] == ["contacts", "leads"]

        es = app.extensions["extraction_service"]
        es.start_scan_async.assert_called_once()
        call_kwargs = es.start_scan_async.call_args.kwargs
        assert call_kwargs["scan_id"] == "s1"
        assert call_kwargs["object_types"] == ["contacts", "leads"]

    def test_unsupported_output_format_returns_400(self, app, client):
        app.extensions[
            "extraction_service"
        ].validate_scan_params.side_effect = ValueError(
            "Unsupported output_format: 'xml'"
        )

        resp = client.post(
            "/api/scan/start",
            json={
                "scan_id": "s1",
                "org_id": "org1",
                "objects": ["contacts"],
                "output_format": "xml",
            },
        )

        assert resp.status_code == 400

    def test_properties_resolved_from_supported_objects(self, app, client):
        client.post(
            "/api/scan/start",
            json={"scan_id": "s1", "org_id": "org1", "objects": ["owners"]},
        )

        es = app.extensions["extraction_service"]
        call_kwargs = es.start_scan_async.call_args.kwargs
        assert call_kwargs["properties_by_object"]["owners"] == []


class TestStatus:
    def test_not_found_returns_404(self, client):
        resp = client.get("/api/scan/nonexistent/status")
        assert resp.status_code == 404

    def test_returns_progress_and_totals(self, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress(
            "s1", "contacts", {"status": "complete", "records_extracted": 100}
        )
        scan_repo.update_object_progress(
            "s1", "companies", {"status": "failed", "records_extracted": 20}
        )

        resp = client.get("/api/scan/s1/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["totals"]["objects_total"] == 2
        assert body["totals"]["objects_complete"] == 1
        assert body["totals"]["objects_failed"] == 1
        assert body["totals"]["records_extracted"] == 120


class TestCancel:
    def test_not_found_returns_404(self, client):
        resp = client.post("/api/scan/nonexistent/cancel")
        assert resp.status_code == 404

    def test_not_running_returns_400(self, app, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        app.extensions["extraction_service"].cancel_scan.return_value = False

        resp = client.post("/api/scan/s1/cancel")

        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_cancels_and_reports_already_complete(self, app, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})
        scan_repo.update_object_progress("s1", "companies", {"status": "in_progress"})
        app.extensions["extraction_service"].cancel_scan.return_value = True

        resp = client.post("/api/scan/s1/cancel")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["objects_already_complete"] == ["contacts"]
        assert body["objects_cancelled"] == ["companies"]


class TestList:
    def test_lists_scans_for_org(self, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.create("s2", "org2", config={})

        resp = client.get("/api/scan/list?org_id=org1")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["scans"][0]["scan_id"] == "s1"


class TestRemove:
    def test_not_found_returns_404(self, client):
        resp = client.delete("/api/scan/nonexistent/remove")
        assert resp.status_code == 404

    def test_removes_scan(self, client, scan_repo):
        scan_repo.create("s1", "org1", config={})

        resp = client.delete("/api/scan/s1/remove")

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        from app.repositories.scan_repository import ScanNotFoundError

        try:
            scan_repo.get("s1")
            assert False, "expected ScanNotFoundError"
        except ScanNotFoundError:
            pass


class TestStatistics:
    def test_aggregates_across_scans(self, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_status("s1", "completed")
        scan_repo.update_object_progress(
            "s1", "contacts", {"status": "complete", "records_extracted": 50}
        )
        scan_repo.create("s2", "org1", config={})
        scan_repo.update_status("s2", "failed")

        resp = client.get("/api/scan/statistics")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_scans"] == 2
        assert body["by_status"] == {"completed": 1, "failed": 1}
        assert body["total_records_extracted"] == 50


class TestResume:
    def test_not_found_returns_404(self, client):
        resp = client.post("/api/scan/nonexistent/resume")
        assert resp.status_code == 404

    def test_wrong_status_returns_400(self, client, scan_repo):
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_status("s1", "completed")

        resp = client.post("/api/scan/s1/resume")

        assert resp.status_code == 400
        assert "nothing to resume" in resp.get_json()["message"]

    def test_all_complete_returns_400(self, client, scan_repo):
        scan_repo.create(
            "s1", "org1", config={"object_types": ["contacts"], "destination": {}}
        )
        scan_repo.update_status("s1", "failed")
        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})

        resp = client.post("/api/scan/s1/resume")

        assert resp.status_code == 400
        assert "already completed" in resp.get_json()["message"]

    def test_resumes_incomplete_types_with_saved_cursor(self, app, client, scan_repo):
        scan_repo.create(
            "s1",
            "org1",
            config={
                "object_types": ["contacts", "companies"],
                "destination": {},
                "output_format": "parquet",
            },
        )
        scan_repo.update_status("s1", "failed")
        scan_repo.update_object_progress("s1", "contacts", {"status": "complete"})
        scan_repo.update_object_progress(
            "s1", "companies", {"status": "failed", "cursor": "saved_cursor_123"}
        )

        resp = client.post("/api/scan/s1/resume")

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["resumed_objects"] == ["companies"]

        es = app.extensions["extraction_service"]
        call_kwargs = es.start_scan_async.call_args.kwargs
        assert call_kwargs["object_types"] == ["companies"]
        assert call_kwargs["after_by_object"] == {"companies": "saved_cursor_123"}
