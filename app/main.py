from flask import Flask

from app.auth.hubspot_auth import HubSpotAuth
from app.clients.hubspot_client import HubSpotClient
from app.config import Settings, validate_settings
from app.logger import logger, werkzeug_logger
from app.routes.health import health_bp


def create_app(settings: Settings) -> Flask:
    werkzeug_logger.setLevel(settings.LOG_LEVEL)
    logger.setLevel(settings.LOG_LEVEL)
    logger.info("Configuration loaded successfully.")
    logger.info("Environment: %s", settings.ENVIRONMENT.upper())
    logger.info("Starting %s v%s", settings.APP_TITLE, settings.APP_VERSION)

    app = Flask(__name__)

    # =========================================================================================
    #                                       Extensions
    # =========================================================================================

    app.extensions["settings"] = settings

    auth = HubSpotAuth(
        base_url=settings.HUBSPOT_BASE_URL,
        api_version=settings.HUBSPOT_API_VERSION,
        access_token=settings.HUBSPOT_ACCESS_TOKEN.get_secret_value(),
        portal_id=settings.HUBSPOT_PORTAL_ID,
    )
    auth.validate()

    app.extensions["client"] = HubSpotClient(
        auth=auth,
        page_size=settings.HUBSPOT_PAGE_SIZE,
        rate_limit=settings.HUBSPOT_RATE_LIMIT_RPS,
        include_associations=settings.HUBSPOT_INCLUDE_ASSOCIATIONS,
    )

    # =========================================================================================
    #                                         Routes
    # =========================================================================================

    app.register_blueprint(health_bp)

    return app


def main():
    settings = validate_settings()
    app = create_app(settings)
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.FLASK_DEBUG)


if __name__ == "__main__":
    main()
