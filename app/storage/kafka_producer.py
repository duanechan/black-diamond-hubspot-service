from confluent_kafka import Producer

from app.logger import logger


class KafkaProducer:
    """Publishes messages to Kafka topics.

    Thin wrapper around `confluent_kafka.Producer`. Messages are buffered
    by `produce()` and only actually sent when `flush()` is called —
    callers control batching by choosing when to flush (e.g. once per
    page, not once per message), since flushing after every single
    message would serialize what should be an async, buffered operation.
    Delivery failures are logged, not raised — publishing is best-effort
    and does not fail an otherwise-successful scan.
    """

    def __init__(self, bootstrap_servers: str) -> None:
        """Initializes the Kafka producer.

        Args:
            bootstrap_servers: Comma-separated host:port pairs of Kafka
                brokers to connect to.
        """
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    def produce(self, topic: str, value: bytes, key: str | None = None) -> None:
        """Buffers a message for publishing to a Kafka topic.

        Does not block or guarantee delivery on its own — call `flush()`
        to actually send buffered messages and confirm delivery.

        Args:
            topic: Kafka topic to publish to.
            value: Message payload, as bytes.
            key: Optional message key, used by Kafka for partition assignment.
        """

        def _delivery_report(err, _msg):
            if err is not None:
                logger.warning(f"Kafka delivery failed for topic '{topic}': {err}")

        self._producer.produce(topic, value=value, key=key, callback=_delivery_report)

    def flush(self, timeout: float = 10.0) -> None:
        """Sends all buffered messages and waits for delivery confirmation.

        Args:
            timeout: Maximum time to wait, in seconds. Any messages still
                undelivered after this are logged as a warning.
        """
        remaining = self._producer.flush(timeout=timeout)
        if remaining > 0:
            logger.warning(
                f"{remaining} Kafka message(s) still undelivered after flush timeout"
            )
