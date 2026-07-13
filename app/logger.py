import logging
import os

from colorlog import ColoredFormatter
from pythonjsonlogger.json import JsonFormatter


def is_json_logging() -> bool:
    return os.environ.get("LOG_FORMAT", "text") == "json"


json_formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
text_formatter = ColoredFormatter(
    "%(asctime_log_color)s%(asctime)s%(reset)s "
    + "%(log_color)s%(levelname)-6s%(reset)s "
    + "%(message)s",
    log_colors={
        "DEBUG": "bold_light_blue",
        "INFO": "bold_white",
        "WARNING": "bold_light_yellow",
        "ERROR": "bold_light_red",
        "CRITICAL": "bold_red",
    },
    secondary_log_colors={
        "asctime": {
            "DEBUG": "light_black",
            "INFO": "light_black",
            "WARNING": "light_black",
            "ERROR": "light_black",
            "CRITICAL": "light_black",
        }
    },
)

handler = logging.StreamHandler()
handler.setFormatter(json_formatter if is_json_logging() else text_formatter)
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.handlers = [handler]
werkzeug_logger.propagate = False

logger = logging.getLogger("app")
logger.addHandler(handler)
logger.propagate = False
