from flask import Flask

from app import config
from app.auth.hubspot_auth import HubSpotAuth
from app.clients.hubspot_client import HubSpotClient
from app.logger import logger


def create_app() -> Flask:
    settings = config.validate_settings()
    logger.setLevel(settings.LOG_LEVEL)

    logger.info("Configuration loaded successfully.")
    logger.info("Environment: %s", settings.ENVIRONMENT.upper())
    logger.info("Starting %s v%s", settings.APP_TITLE, settings.APP_VERSION)

    app = Flask(__name__)
    auth = HubSpotAuth(
        base_url=settings.HUBSPOT_BASE_URL,
        api_version=settings.HUBSPOT_API_VERSION,
        access_token=settings.HUBSPOT_ACCESS_TOKEN.get_secret_value(),
        portal_id=settings.HUBSPOT_PORTAL_ID,
    )
    auth.validate()

    app.extensions["settings"] = settings
    app.extensions["auth"] = auth
    app.extensions["client"] = HubSpotClient(
        auth=auth,
        page_size=settings.HUBSPOT_PAGE_SIZE,
        rate_limit=settings.HUBSPOT_RATE_LIMIT_RPS,
        include_associations=settings.HUBSPOT_INCLUDE_ASSOCIATIONS,
    )

    return app


def main():
    create_app()


if __name__ == "__main__":
    main()
