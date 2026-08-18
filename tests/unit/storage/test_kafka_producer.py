from unittest.mock import MagicMock, patch

from app.storage.kafka_producer import KafkaProducer


def make_producer(mock_producer=None):
    mock_producer = mock_producer or MagicMock()
    with patch(
        "app.storage.kafka_producer.Producer", return_value=mock_producer
    ) as mock_producer_cls:
        kp = KafkaProducer(bootstrap_servers="localhost:9092")
    return kp, mock_producer, mock_producer_cls


class TestConstruction:
    def test_configures_bootstrap_servers(self):
        kp, mock_producer, mock_producer_cls = make_producer()
        mock_producer_cls.assert_called_once_with(
            {"bootstrap.servers": "localhost:9092"}
        )


class TestPing:
    def test_true_when_reachable(self):
        kp, mock_producer, _ = make_producer()
        assert kp.ping() is True
        mock_producer.list_topics.assert_called_once_with(timeout=5.0)

    def test_false_on_exception_not_raised(self):
        kp, mock_producer, _ = make_producer()
        mock_producer.list_topics.side_effect = Exception("broker unreachable")

        assert kp.ping() is False


class TestProduce:
    def test_buffers_message_with_topic_value_key(self):
        kp, mock_producer, _ = make_producer()

        kp.produce("hs.contacts.dev", value=b"payload", key="scan-1")

        call_args = mock_producer.produce.call_args
        assert call_args.args[0] == "hs.contacts.dev"
        assert call_args.kwargs["value"] == b"payload"
        assert call_args.kwargs["key"] == "scan-1"
        assert callable(call_args.kwargs["callback"])

    def test_delivery_callback_logs_warning_on_error(self):
        kp, mock_producer, _ = make_producer()
        kp.produce("hs.contacts.dev", value=b"payload")
        callback = mock_producer.produce.call_args.kwargs["callback"]

        with patch("app.storage.kafka_producer.logger") as mock_logger:
            callback("some broker error", MagicMock())
            mock_logger.warning.assert_called_once()
            assert "hs.contacts.dev" in mock_logger.warning.call_args.args[0]

    def test_delivery_callback_silent_on_success(self):
        kp, mock_producer, _ = make_producer()
        kp.produce("hs.contacts.dev", value=b"payload")
        callback = mock_producer.produce.call_args.kwargs["callback"]

        with patch("app.storage.kafka_producer.logger") as mock_logger:
            callback(None, MagicMock())
            mock_logger.warning.assert_not_called()

    def test_does_not_flush_on_its_own(self):
        kp, mock_producer, _ = make_producer()

        kp.produce("hs.contacts.dev", value=b"payload")

        mock_producer.flush.assert_not_called()


class TestFlush:
    def test_flushes_with_given_timeout(self):
        kp, mock_producer, _ = make_producer()
        mock_producer.flush.return_value = 0

        kp.flush(timeout=5.0)

        mock_producer.flush.assert_called_once_with(timeout=5.0)

    def test_warns_when_messages_remain_undelivered(self):
        kp, mock_producer, _ = make_producer()
        mock_producer.flush.return_value = 3

        with patch("app.storage.kafka_producer.logger") as mock_logger:
            kp.flush()
            mock_logger.warning.assert_called_once()
            assert "3" in mock_logger.warning.call_args.args[0]

    def test_no_warning_when_all_delivered(self):
        kp, mock_producer, _ = make_producer()
        mock_producer.flush.return_value = 0

        with patch("app.storage.kafka_producer.logger") as mock_logger:
            kp.flush()
            mock_logger.warning.assert_not_called()
