import threading
from unittest.mock import MagicMock

import pytest

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError
from app.services.extraction_service import ExtractionService
from app.storage.clickhouse_client import ClickHouseClientError
from app.storage.minio_client import MinioClientError


def make_service(
    scan_repo,
    client=None,
    minio=None,
    kafka=None,
    clickhouse=None,
    pii=None,
    normalizer=None,
    environment="dev",
):
    return ExtractionService(
        normalizer=normalizer or MagicMock(),
        minio=minio or MagicMock(),
        kafka=kafka or MagicMock(),
        pii=pii or MagicMock(mask=lambda page: page),
        clickhouse=clickhouse or MagicMock(),
        client=client or MagicMock(spec=HubSpotClient),
        scans=scan_repo,
        environment=environment,
    )


def make_paged_iterator(pages, fail_on_page=None):
    """Builds an iter_objects-shaped side_effect function.

    `pages` is a list of (cursor, records) tuples. Resumes from the
    page whose predecessor's cursor matches `after`. Raises
    HubSpotClientError instead of yielding when the 1-indexed page
    number equals `fail_on_page`.
    """

    def _iter(
        object_type,
        properties,
        associations=None,
        last_modified_after_ms=None,
        after=None,
    ):
        start_idx = 0
        if after is not None:
            for i, (cursor, _) in enumerate(pages):
                if cursor == after:
                    start_idx = i + 1
                    break
        for i, (cursor, records) in enumerate(pages[start_idx:], start=start_idx + 1):
            if fail_on_page == i:
                raise HubSpotClientError("simulated API failure")
            yield cursor, records

    return _iter


ONE_PAGE = lambda records: lambda *a, **kw: iter([(None, records)])


class TestValidateScanParams:
    def test_none_output_format_does_not_raise(self, scan_repo):
        make_service(scan_repo).validate_scan_params(None, {})

    @pytest.mark.parametrize("fmt", ["json", "parquet"])
    def test_valid_formats_do_not_raise(self, scan_repo, fmt):
        make_service(scan_repo).validate_scan_params(fmt, {})

    def test_unsupported_format_raises_value_error(self, scan_repo):
        with pytest.raises(ValueError, match="Unsupported output_format"):
            make_service(scan_repo).validate_scan_params("xml", {})


class TestCancelScan:
    def test_returns_false_for_unknown_scan_id(self, scan_repo):
        svc = make_service(scan_repo)
        assert svc.cancel_scan("nonexistent") is False

    def test_returns_true_while_scan_is_running(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        started = threading.Event()
        proceed = threading.Event()

        def _iter(*a, **kw):
            started.set()
            proceed.wait(timeout=5)
            yield None, [{"id": "1", "properties": {}}]

        client.iter_objects.side_effect = _iter
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        assert started.wait(timeout=5)
        assert svc.cancel_scan("s1") is True
        proceed.set()
        t.join()

    def test_returns_false_after_scan_finishes(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        assert svc.cancel_scan("s1") is False


class TestMinioDestination:
    def test_uploads_page_and_metadata_when_output_format_and_bucket_set(
        self, scan_repo
    ):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        minio = MagicMock()
        minio.upload.return_value = "org1/s1/contacts/page_1.json"
        minio.upload_metadata.return_value = "org1/s1/contacts/_metadata.json"
        normalizer = MagicMock(to_json=lambda records: b"[]")
        svc = make_service(scan_repo, client, minio=minio, normalizer=normalizer)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            output_format="json",
            destination={"minio_bucket": "my-bucket"},
        )
        t.join()

        upload_kwargs = minio.upload.call_args.kwargs
        assert upload_kwargs["org_id"] == "org1"
        assert upload_kwargs["scan_id"] == "s1"
        assert upload_kwargs["object_type"] == "contacts"
        assert upload_kwargs["page"] == 1
        assert upload_kwargs["output_format"] == "json"

        metadata_kwargs = minio.upload_metadata.call_args.kwargs
        assert metadata_kwargs["object_type"] == "contacts"

        progress = scan_repo.get("s1").progress["contacts"]
        assert progress["minio_path"] == "s3://my-bucket/org1/s1/contacts/"

    def test_not_uploaded_when_output_format_is_none(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        minio = MagicMock()
        svc = make_service(scan_repo, client, minio=minio)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            output_format=None,
            destination={"minio_bucket": "my-bucket"},
        )
        t.join()

        minio.upload.assert_not_called()

    def test_not_uploaded_when_no_minio_bucket_in_destination(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        minio = MagicMock()
        svc = make_service(scan_repo, client, minio=minio)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            output_format="json",
            destination={},
        )
        t.join()

        minio.upload.assert_not_called()


class TestKafkaDestination:
    def test_publishes_one_message_per_record_to_correct_topic(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE(
            [
                {"id": "1", "properties": {"email": "a@x.com"}},
                {"id": "2", "properties": {"email": "b@x.com"}},
            ]
        )
        kafka = MagicMock()
        svc = make_service(scan_repo, client, kafka=kafka, environment="dev")

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={"kafka_publish": True},
        )
        t.join()

        assert kafka.produce.call_count == 2
        topic = kafka.produce.call_args_list[0].args[0]
        assert topic == "hs.contacts.dev"
        kafka.flush.assert_called_once()

    def test_message_shape_includes_meta_and_record(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE(
            [{"id": "1", "properties": {"email": "a@x.com"}}]
        )
        kafka = MagicMock()
        svc = make_service(scan_repo, client, kafka=kafka)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={"kafka_publish": True},
        )
        t.join()

        import json

        message = json.loads(kafka.produce.call_args.kwargs["value"])
        assert message["meta"]["object"] == "contacts"
        assert message["meta"]["org_id"] == "org1"
        assert message["meta"]["scan_id"] == "s1"
        assert message["record"]["hs_object_id"] == "1"
        assert message["record"]["email"] == "a@x.com"

    def test_pii_masking_applied_before_publish(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE(
            [{"id": "1", "properties": {"email": "a@x.com"}}]
        )
        kafka = MagicMock()
        pii = MagicMock()
        pii.mask.side_effect = lambda page: [
            {**r, "properties": {**r["properties"], "email": "MASKED"}} for r in page
        ]
        svc = make_service(scan_repo, client, kafka=kafka, pii=pii)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={"kafka_publish": True},
        )
        t.join()

        pii.mask.assert_called_once()
        import json

        message = json.loads(kafka.produce.call_args.kwargs["value"])
        assert message["record"]["email"] == "MASKED"

    def test_not_published_when_kafka_publish_not_requested(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        kafka = MagicMock()
        svc = make_service(scan_repo, client, kafka=kafka)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        kafka.produce.assert_not_called()


class TestClickHouseDestination:
    def test_loaded_when_requested(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        page = [{"id": "1", "properties": {}}]
        client.iter_objects.side_effect = ONE_PAGE(page)
        clickhouse = MagicMock()
        svc = make_service(scan_repo, client, clickhouse=clickhouse)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={"clickhouse_load": True},
        )
        t.join()

        clickhouse.insert_records.assert_called_once_with("contacts", page)

    def test_not_loaded_when_not_requested(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        clickhouse = MagicMock()
        svc = make_service(scan_repo, client, clickhouse=clickhouse)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        clickhouse.insert_records.assert_not_called()

    def test_all_three_destinations_fire_together(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        minio, kafka, clickhouse = MagicMock(), MagicMock(), MagicMock()
        normalizer = MagicMock(to_json=lambda records: b"[]")
        svc = make_service(
            scan_repo,
            client,
            minio=minio,
            kafka=kafka,
            clickhouse=clickhouse,
            normalizer=normalizer,
        )

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            output_format="json",
            destination={
                "minio_bucket": "b",
                "kafka_publish": True,
                "clickhouse_load": True,
            },
        )
        t.join()

        assert minio.upload.called
        assert kafka.produce.called
        assert clickhouse.insert_records.called


class TestObjectTypeRouting:
    def test_owners_routed_to_iter_owners(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_owners.return_value = iter(
            [(None, [{"id": "1", "properties": {}}])]
        )
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1", "org1", ["owners"], {"owners": []}, {"owners": []}, destination={}
        )
        t.join()

        assert client.iter_owners.called
        assert not client.iter_objects.called

    def test_engagements_routed_to_iter_engagements(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_engagements.return_value = iter(
            [(None, [{"id": "1", "properties": {}}])]
        )
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["engagements"],
            {"engagements": []},
            {"engagements": []},
            destination={},
        )
        t.join()

        assert client.iter_engagements.called
        assert not client.iter_objects.called

    def test_standard_type_routed_to_iter_objects_with_full_args(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": ["email"]},
            {"contacts": ["companies"]},
            last_modified_after_ms=12345,
            destination={},
        )
        t.join()

        call_kwargs = client.iter_objects.call_args.kwargs
        assert call_kwargs["associations"] == ["companies"]
        assert call_kwargs["last_modified_after_ms"] == 12345


class TestErrorHandling:
    def test_hubspot_client_error_marks_failed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = HubSpotClientError("boom")
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        progress = scan_repo.get("s1").progress["contacts"]
        assert progress["status"] == "failed"
        assert "boom" in progress["error"]

    def test_minio_client_error_marks_failed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        minio = MagicMock()
        minio.upload.side_effect = MinioClientError("upload failed")
        normalizer = MagicMock(to_json=lambda records: b"[]")
        svc = make_service(scan_repo, client, minio=minio, normalizer=normalizer)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            output_format="json",
            destination={"minio_bucket": "b"},
        )
        t.join()

        assert scan_repo.get("s1").progress["contacts"]["status"] == "failed"

    def test_clickhouse_client_error_marks_failed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        clickhouse = MagicMock()
        clickhouse.insert_records.side_effect = ClickHouseClientError("insert failed")
        svc = make_service(scan_repo, client, clickhouse=clickhouse)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={"clickhouse_load": True},
        )
        t.join()

        assert scan_repo.get("s1").progress["contacts"]["status"] == "failed"

    def test_missing_kafka_topic_marks_failed_with_clear_message(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        svc = make_service(scan_repo, client)

        # "widgets" is not a real object type / not in KAFKA_TOPIC_PREFIX_BY_OBJECT
        t = svc.start_scan_async(
            "s1",
            "org1",
            ["widgets"],
            {"widgets": []},
            {"widgets": []},
            destination={"kafka_publish": True},
        )
        t.join()

        progress = scan_repo.get("s1").progress["widgets"]
        assert progress["status"] == "failed"
        assert "No Kafka topic configured" in progress["error"]

    def test_generic_exception_marks_failed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = RuntimeError("unexpected")
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        assert scan_repo.get("s1").progress["contacts"]["status"] == "failed"

    def test_one_object_type_failing_does_not_stop_others(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)

        def _iter(object_type, *a, **kw):
            if object_type == "contacts":
                raise HubSpotClientError("contacts failed")
            yield None, [{"id": "1", "properties": {}}]

        client.iter_objects.side_effect = _iter
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts", "companies"],
            {"contacts": [], "companies": []},
            {"contacts": [], "companies": []},
            destination={},
        )
        t.join()

        progress = scan_repo.get("s1").progress
        assert progress["contacts"]["status"] == "failed"
        assert progress["companies"]["status"] == "complete"


class TestFinalStatusAggregation:
    def test_all_complete_is_completed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = ONE_PAGE([{"id": "1", "properties": {}}])
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        assert scan_repo.get("s1").status == "completed"

    def test_any_failed_is_failed(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = HubSpotClientError("boom")
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        assert scan_repo.get("s1").status == "failed"

    def test_cancelled_mid_scan_is_cancelled(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        svc_holder = {}

        def _iter(*a, **kw):
            svc_holder["svc"].cancel_scan("s1")
            yield None, [{"id": "1", "properties": {}}]

        client.iter_objects.side_effect = _iter
        svc = make_service(scan_repo, client)
        svc_holder["svc"] = svc

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        assert scan_repo.get("s1").status == "cancelled"
        assert scan_repo.get("s1").progress["contacts"]["status"] == "cancelled"


class TestCheckpointing:
    def test_cursor_persisted_after_each_page(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = make_paged_iterator(
            [
                ("c1", [{"id": "1", "properties": {}}]),
                (None, [{"id": "2", "properties": {}}]),
            ]
        )
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        progress = scan_repo.get("s1").progress["contacts"]
        assert progress["status"] == "complete"
        assert progress["records_extracted"] == 2
        assert progress["pages_downloaded"] == 2
        assert progress["cursor"] is None  # final page has no next cursor

    def test_failure_preserves_partial_progress_and_cursor(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = make_paged_iterator(
            [
                ("c1", [{"id": "1", "properties": {}}]),
                (None, [{"id": "2", "properties": {}}]),
            ],
            fail_on_page=2,
        )
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        progress = scan_repo.get("s1").progress["contacts"]
        assert progress["status"] == "failed"
        assert progress["cursor"] == "c1"
        assert progress["records_extracted"] == 1
        assert progress["pages_downloaded"] == 1


class TestResume:
    def test_resume_calls_iter_objects_with_saved_cursor(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        pages = [
            ("c1", [{"id": "1", "properties": {}}]),
            (None, [{"id": "2", "properties": {}}]),
        ]
        client.iter_objects.side_effect = make_paged_iterator(pages, fail_on_page=2)
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()
        saved_cursor = scan_repo.get("s1").progress["contacts"]["cursor"]
        assert saved_cursor == "c1"

        client.iter_objects.side_effect = make_paged_iterator(pages)
        t2 = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
            after_by_object={"contacts": saved_cursor},
        )
        t2.join()

        last_call_kwargs = client.iter_objects.call_args.kwargs
        assert last_call_kwargs["after"] == "c1"

    def test_resume_totals_are_cumulative_not_reset(self, scan_repo):
        scan_repo.create("s1", "org1", config={})
        client = MagicMock(spec=HubSpotClient)
        pages = [
            ("c1", [{"id": "1", "properties": {}}]),
            ("c2", [{"id": "2", "properties": {}}]),
            (None, [{"id": "3", "properties": {}}]),
        ]
        client.iter_objects.side_effect = make_paged_iterator(pages, fail_on_page=2)
        svc = make_service(scan_repo, client)

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
        )
        t.join()

        client.iter_objects.side_effect = make_paged_iterator(pages)
        saved_cursor = scan_repo.get("s1").progress["contacts"]["cursor"]
        t2 = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
            after_by_object={"contacts": saved_cursor},
        )
        t2.join()

        progress = scan_repo.get("s1").progress["contacts"]
        assert progress["status"] == "complete"
        assert progress["records_extracted"] == 3
        assert progress["pages_downloaded"] == 3

    def test_resume_with_no_saved_cursor_starts_from_page_one(self, scan_repo):
        """Backward compatibility: a pre-checkpointing failure entry
        with no "cursor" key at all must not crash, and must fall back
        to starting from page 1."""
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress(
            "s1", "contacts", {"status": "failed", "error": "old failure"}
        )

        client = MagicMock(spec=HubSpotClient)
        client.iter_objects.side_effect = make_paged_iterator(
            [(None, [{"id": "1", "properties": {}}])]
        )
        svc = make_service(scan_repo, client)

        prior_cursor = scan_repo.get("s1").progress["contacts"].get("cursor")
        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts"],
            {"contacts": []},
            {"contacts": []},
            destination={},
            after_by_object={"contacts": prior_cursor},
        )
        t.join()

        assert client.iter_objects.call_args.kwargs["after"] is None
        assert scan_repo.get("s1").progress["contacts"]["status"] == "complete"


class TestCancelBeforeStart:
    def test_cancel_before_object_type_starts_preserves_prior_progress(self, scan_repo):
        """If cancel fires before an object type's turn in the loop, its
        prior progress (from an earlier run) must be preserved, not
        wiped down to a bare {"status": "cancelled"}."""
        scan_repo.create("s1", "org1", config={})
        scan_repo.update_object_progress(
            "s1",
            "companies",
            {"status": "failed", "records_extracted": 50, "cursor": "old_cursor"},
        )

        client = MagicMock(spec=HubSpotClient)
        svc_holder = {}

        def _iter(*args, **kwargs):
            svc_holder["svc"].cancel_scan("s1")
            yield None, [{"id": "1", "properties": {}}]

        client.iter_objects.side_effect = _iter
        svc = make_service(scan_repo, client)
        svc_holder["svc"] = svc

        t = svc.start_scan_async(
            "s1",
            "org1",
            ["contacts", "companies"],
            {"contacts": [], "companies": []},
            {"contacts": [], "companies": []},
            destination={},
        )
        t.join()

        companies_progress = scan_repo.get("s1").progress["companies"]
        assert companies_progress["status"] == "cancelled"
        assert companies_progress["records_extracted"] == 50
        assert companies_progress["cursor"] == "old_cursor"
