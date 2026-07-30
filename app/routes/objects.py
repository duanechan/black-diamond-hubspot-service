from flask_restx import Namespace, Resource

from app.auth.hmac_auth import require_hmac
from app.constants import SUPPORTED_OBJECTS

objects_ns = Namespace("objects", description="Supported HubSpot objects")


@objects_ns.route("/")
class Objects(Resource):
    @require_hmac()
    def get(self):
        return {
            "supported_objects": [
                {"name": name, **info} for name, info in SUPPORTED_OBJECTS.items()
            ]
        }, 200
