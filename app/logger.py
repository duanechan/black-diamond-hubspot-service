import logging

from colorlog import ColoredFormatter
from pythonjsonlogger.json import JsonFormatter

handler = logging.StreamHandler()

json_formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
text_formatter = ColoredFormatter(
    "%(asctime_log_color)s%(asctime)s%(reset)s " +
    "%(log_color)s%(levelname)-6s%(reset)s " +
    "%(message)s",
    log_colors={
        "DEBUG": "bold_light_blue",
        "INFO": "bold_white",
        "WARNING": "bold_light_yellow",
        "ERROR": "bold_light_red",
    },
    secondary_log_colors={
        "asctime": {
            "DEBUG": "light_black",
            "INFO": "light_black",
            "WARNING": "light_black",
            "ERROR": "light_black",
        }
    },
)

logger = logging.getLogger("app")
logger.addHandler(handler)
logger.propagate = False
