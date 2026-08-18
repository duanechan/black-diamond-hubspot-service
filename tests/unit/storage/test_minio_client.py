from unittest.mock import MagicMock, patch

import pytest

from app.storage.minio_client import MinioClient, MinioClientError


def make_client(enabled=True, mock_minio=None):
    mock_minio = mock_minio or MagicMock()
    mock_minio.bucket_exists.return_value = True
    with patch("app.storage.minio_client.Minio", return_value=mock_minio):
        client = MinioClient(
            enabled=enabled,
            endpoint="localhost:9000",
            access_key="key",
            secret_key="secret",
            secure=False,
            bucket="my-bucket",
        )
    return client, mock_minio


class TestConstruction:
    def test_disabled_never_constructs_minio_client(self):
        with patch("app.storage.minio_client.Minio") as mock_minio_cls:
            MinioClient(
                enabled=False,
                endpoint="localhost:9000",
                access_key="key",
                secret_key="secret",
                secure=False,
                bucket="my-bucket",
            )
        mock_minio_cls.assert_not_called()

    def test_enabled_checks_bucket_exists(self):
        client, mock_minio = make_client(enabled=True)
        mock_minio.bucket_exists.assert_called_once_with("my-bucket")

    def test_enabled_raises_if_bucket_missing(self):
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = False

        with patch("app.storage.minio_client.Minio", return_value=mock_minio):
            with pytest.raises(MinioClientError, match="does not exist"):
                MinioClient(
                    enabled=True,
                    endpoint="localhost:9000",
                    access_key="key",
                    secret_key="secret",
                    secure=False,
                    bucket="missing-bucket",
                )


class TestPing:
    def test_disabled_returns_false_without_connecting(self):
        client, mock_minio = make_client(enabled=False)
        assert client.ping() is False
        mock_minio.list_buckets.assert_not_called()

    def test_enabled_true_when_reachable(self):
        client, mock_minio = make_client(enabled=True)
        assert client.ping() is True

    def test_enabled_false_on_exception(self):
        client, mock_minio = make_client(enabled=True)
        mock_minio.list_buckets.side_effect = Exception("connection refused")
        assert client.ping() is False


class TestUpload:
    def test_disabled_is_a_noop_returning_none(self):
        client, mock_minio = make_client(enabled=False)
        result = client.upload(
            data=b"data",
            org_id="org1",
            scan_id="scan1",
            object_type="contacts",
            page=1,
            output_format="json",
        )
        assert result is None
        mock_minio.put_object.assert_not_called()

    def test_uploads_with_page_numbered_key(self):
        client, mock_minio = make_client(enabled=True)

        key = client.upload(
            data=b"some-bytes",
            org_id="org1",
            scan_id="scan1",
            object_type="contacts",
            page=3,
            output_format="parquet",
        )

        assert key == "org1/scan1/contacts/page_3.parquet"
        call_kwargs = mock_minio.put_object.call_args.kwargs
        assert call_kwargs["bucket_name"] == "my-bucket"
        assert call_kwargs["object_name"] == "org1/scan1/contacts/page_3.parquet"
        assert call_kwargs["length"] == len(b"some-bytes")

    def test_raises_minio_client_error_on_failure(self):
        client, mock_minio = make_client(enabled=True)
        mock_minio.put_object.side_effect = Exception("network error")

        with pytest.raises(MinioClientError):
            client.upload(
                data=b"x",
                org_id="org1",
                scan_id="scan1",
                object_type="contacts",
                page=1,
                output_format="json",
            )


class TestUploadMetadata:
    def test_disabled_is_a_noop_returning_none(self):
        client, mock_minio = make_client(enabled=False)
        result = client.upload_metadata(
            org_id="org1", scan_id="scan1", object_type="contacts", data=b"{}"
        )
        assert result is None
        mock_minio.put_object.assert_not_called()

    def test_uses_fixed_metadata_key_not_page_numbered(self):
        client, mock_minio = make_client(enabled=True)

        key = client.upload_metadata(
            org_id="org1", scan_id="scan1", object_type="contacts", data=b"{}"
        )

        assert key == "org1/scan1/contacts/_metadata.json"

    def test_raises_minio_client_error_on_failure(self):
        client, mock_minio = make_client(enabled=True)
        mock_minio.put_object.side_effect = Exception("network error")

        with pytest.raises(MinioClientError):
            client.upload_metadata(
                org_id="org1", scan_id="scan1", object_type="contacts", data=b"{}"
            )
