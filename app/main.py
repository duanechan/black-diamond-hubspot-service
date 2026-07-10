from app import config
from app.logger import json_formatter, text_formatter, handler, logger

def create_app():
    settings = config.validate_settings()
    logger.setLevel(settings.LOG_LEVEL)
    handler.setFormatter(json_formatter if settings.LOG_FORMAT == "json" else text_formatter)

    logger.info("Configuration loaded successfully.")
    logger.info("Environment: %s", settings.ENVIRONMENT.upper())
    logger.info("Starting %s v%s", settings.APP_TITLE, settings.APP_VERSION)


def main():
    create_app()


if __name__ == "__main__":
    main()
