import logging

from colorlog import ColoredFormatter

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(
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
))

logger = logging.getLogger(__name__)
logger.setLevel("INFO")
logger.addHandler(handler)
