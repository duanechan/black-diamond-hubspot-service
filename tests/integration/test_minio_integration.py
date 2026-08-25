from tests.integration.conftest import (
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_TEST_BUCKET,
)


class TestMinioIntegration:
    def test_ping_returns_true_when_reachable(self, real_minio_client):
        assert real_minio_client.ping() is True

    def test_upload_creates_retrievable_object(self, real_minio_client):
        from minio import Minio

        key = real_minio_client.upload(
            data=b'{"hello": "world"}',
            org_id="test-org",
            scan_id="test-scan",
            object_type="contacts",
            page=1,
            output_format="json",
        )

        assert key == "test-org/test-scan/contacts/page_1.json"

        raw = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        response = raw.get_object(MINIO_TEST_BUCKET, key)
        try:
            assert response.read() == b'{"hello": "world"}'
        finally:
            response.close()
            response.release_conn()
            raw.remove_object(MINIO_TEST_BUCKET, key)

    def test_upload_metadata_creates_retrievable_object(self, real_minio_client):
        from minio import Minio

        key = real_minio_client.upload_metadata(
            org_id="test-org",
            scan_id="test-scan",
            object_type="contacts",
            data=b'{"total": 5}',
        )

        assert key == "test-org/test-scan/contacts/_metadata.json"

        raw = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        response = raw.get_object(MINIO_TEST_BUCKET, key)
        try:
            assert response.read() == b'{"total": 5}'
        finally:
            response.close()
            response.release_conn()
            raw.remove_object(MINIO_TEST_BUCKET, key)
