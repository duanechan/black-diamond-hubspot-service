import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.repositories.scan_repository import ScanRepository
from app.storage.clickhouse_client import ClickHouseClient
from app.storage.kafka_producer import KafkaProducer
from app.storage.minio_client import MinioClient

POSTGRES_URL = "postgresql+psycopg://dev_user:dev_pass@localhost:5432/hubspot_dev"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_TEST_BUCKET = "hubspot-test"
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
CLICKHOUSE_HOST = "localhost"
CLICKHOUSE_PORT = 8123
CLICKHOUSE_USER = "default"
CLICKHOUSE_PASSWORD = "default"
CLICKHOUSE_DATABASE = "hubspot"


@pytest.fixture
def real_scan_repo():
    """A ScanRepository backed by the real docker-compose Postgres.

    Skips (doesn't fail) if Postgres isn't reachable, so this suite is
    safe to run without `docker compose up`.
    """
    try:
        engine = create_engine(POSTGRES_URL)
        with engine.connect():
            pass
    except Exception as e:
        pytest.skip(f"Postgres not reachable at {POSTGRES_URL}: {e}")

    Base.metadata.create_all(engine)
    return ScanRepository(sessionmaker(bind=engine))


@pytest.fixture
def unique_scan_id():
    """A fresh scan_id per test, so tests never collide with leftover
    rows from a previous run against the real, persistent database."""
    return f"test-{uuid.uuid4()}"


@pytest.fixture
def real_minio_client():
    """A MinioClient backed by the real docker-compose MinIO.

    Creates the test bucket if it doesn't already exist (mirrors what a
    real deployment's bootstrapping would do). Skips if MinIO isn't
    reachable.
    """
    try:
        from minio import Minio

        raw_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        if not raw_client.bucket_exists(MINIO_TEST_BUCKET):
            raw_client.make_bucket(MINIO_TEST_BUCKET)
    except Exception as e:
        pytest.skip(f"MinIO not reachable at {MINIO_ENDPOINT}: {e}")

    return MinioClient(
        enabled=True,
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
        bucket=MINIO_TEST_BUCKET,
    )


@pytest.fixture
def real_kafka_producer():
    """A KafkaProducer backed by the real docker-compose Kafka.

    Skips if the broker isn't reachable.
    """
    producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    if not producer.ping():
        pytest.skip(f"Kafka not reachable at {KAFKA_BOOTSTRAP_SERVERS}")
    return producer


@pytest.fixture
def real_clickhouse_client():
    """A ClickHouseClient backed by the real docker-compose ClickHouse.

    Skips if the server isn't reachable.
    """
    client = ClickHouseClient(
        enabled=True,
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DATABASE,
    )
    if not client.ping():
        pytest.skip(f"ClickHouse not reachable at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}")
    return client
