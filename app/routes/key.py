from flask_restx import Namespace, Resource

from app.auth.hmac_auth import require_hmac

key_ns = Namespace("key", description="HMAC key verification")


@key_ns.route("/verify")
class Verify(Resource):
    @require_hmac()
    def get(self):
        return {"valid": True, "message": "HMAC key verified"}, 200
