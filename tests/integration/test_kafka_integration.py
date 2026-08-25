import uuid

from confluent_kafka import Consumer

from tests.integration.conftest import KAFKA_BOOTSTRAP_SERVERS


class TestKafkaIntegration:
    def test_ping_returns_true_when_reachable(self, real_kafka_producer):
        assert real_kafka_producer.ping() is True

    def test_produce_and_flush_delivers_message(self, real_kafka_producer):
        topic = f"test-topic-{uuid.uuid4()}"
        real_kafka_producer.produce(topic, value=b"hello-kafka", key="test-key")
        real_kafka_producer.flush()

        consumer = Consumer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                "group.id": f"test-group-{uuid.uuid4()}",
                "auto.offset.reset": "earliest",
            }
        )
        try:
            consumer.subscribe([topic])
            msg = None
            for _ in range(20):
                msg = consumer.poll(timeout=1.0)
                if msg is not None:
                    break

            assert msg is not None, "message was not delivered within timeout"
            assert msg.error() is None
            assert msg.value() == b"hello-kafka"
            assert msg.key().decode() == "test-key"
        finally:
            consumer.close()
