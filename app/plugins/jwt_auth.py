import jwt

from .base import BasePlugin
from .errors import (
    JWTInvalidTokenError,
    JWTMissingAuthHeaderError,
    JWTMissingTenantError,
)

SECRET = "super-secret"
ALGORITHM = "HS256"

class JWTAuthPlugin(BasePlugin):
    name = "jwt_auth"
    order = 5

    async def before_request(self, context):
        headers = {
            k.decode(): v.decode()
            for k, v in context.scope["headers"]
        }

        auth = headers.get("authorization")
        if not auth or not auth.startswith("Bearer "):
            raise JWTMissingAuthHeaderError()

        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        except jwt.PyJWTError as exc:
            raise JWTInvalidTokenError() from exc

        tenant = payload.get("tenant_id")
        if not tenant:
            raise JWTMissingTenantError()

        context.tenant = tenant