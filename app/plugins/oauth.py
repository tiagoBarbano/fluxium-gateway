import time
import jwt
from jwt import PyJWKClient

from .base import BasePlugin
from .errors import (
    JWTMissingAuthHeaderError,
    JWTInvalidTokenError,
    JWTInvalidScopeError,
)

class KeycloakOAuth2Plugin(BasePlugin):
    name = "oauth2"
    order = 1

    def __init__(
        self,
        issuer: str,
        audience: str,
        required_scopes: list[str] | None = None,
        jwks_cache_ttl: int = 300,
    ):
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.required_scopes = required_scopes or []
        self.jwks_url = f"{self.issuer}/protocol/openid-connect/certs"

        self._jwks_client = PyJWKClient(self.jwks_url)
        self._jwks_last_refresh = 0
        self._jwks_cache_ttl = jwks_cache_ttl

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
            signing_key = self._get_signing_key(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )

        except Exception as exc:
            raise JWTInvalidTokenError() from exc

        # 🔎 Validar scopes
        token_scopes = payload.get("scope", "")
        token_scopes = token_scopes.split()

        if self.required_scopes:
            if not any(scope in token_scopes for scope in self.required_scopes):
                raise JWTInvalidScopeError()

        # 🔐 Extrair informações úteis
        context.user_id = payload.get("sub")
        context.client_id = payload.get("azp")  # authorized party
        context.scopes = token_scopes
        context.roles = self._extract_roles(payload)

    def _get_signing_key(self, token: str):
        """
        Faz refresh periódico do JWKS para evitar usar chave expirada.
        """
        now = time.time()

        if now - self._jwks_last_refresh > self._jwks_cache_ttl:
            self._jwks_client = PyJWKClient(self.jwks_url)
            self._jwks_last_refresh = now

        return self._jwks_client.get_signing_key_from_jwt(token)

    def _extract_roles(self, payload: dict) -> list[str]:
        roles = []

        # Roles globais
        realm_access = payload.get("realm_access", {})
        roles.extend(realm_access.get("roles", []))

        # Roles específicas da aplicação
        resource_access = payload.get("resource_access", {})
        client_roles = resource_access.get(self.audience, {})
        roles.extend(client_roles.get("roles", []))

        return roles