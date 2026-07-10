from app import config
from app.logger import logger

def create_app():
    settings = config.validate_settings()
    logger.setLevel(settings.LOG_LEVEL)

    logger.info("Configuration loaded successfully.")
    logger.info("Environment: %s", settings.ENVIRONMENT.upper())
    logger.info("Starting %s v%s", settings.APP_TITLE, settings.APP_VERSION)


def main():
    create_app()


if __name__ == "__main__":
    main()
