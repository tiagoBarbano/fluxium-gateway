import os
from urllib.parse import parse_qs

from app.config_store import db

from .base import BasePlugin
from .errors import APIKeyInvalidError, APIKeyMissingError


class APIKeyAuthPlugin(BasePlugin):
    name = "api_key"
    order = 4

    @property
    def _consumers_collection(self):
        return db.consumers

    def _plugin_config(self, context):
        for plugin in context.route.get("plugins", []):
            if isinstance(plugin, dict) and plugin.get("type") == self.name:
                return plugin.get("config", {})
        return {}

    def _headers_map(self, context):
        return {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in context.scope.get("headers", [])
        }

    def _query_map(self, context):
        raw = context.scope.get("query_string", b"")
        return parse_qs(raw.decode("latin-1"), keep_blank_values=False)

    def _configured_keys(self, config):
        keys_cfg = config.get("keys")
        if isinstance(keys_cfg, list):
            return {str(item) for item in keys_cfg if str(item).strip()}

        keys_env = os.getenv("GATEWAY_API_KEYS", "")
        if not keys_env.strip():
            return set()

        return {item.strip() for item in keys_env.split(",") if item.strip()}

    async def _resolve_consumer(self, context, api_key, enforce_resolution):
        tenant_id = context.route.get("tenant_id") or context.tenant
        if not tenant_id:
            if enforce_resolution:
                raise APIKeyInvalidError("Tenant is required to resolve consumer")
            return None

        consumer = await self._consumers_collection.find_one(
            {
                "tenant_id": tenant_id,
                "api_keys": api_key,
                "status": {"$ne": "inactive"},
            }
        )

        if not consumer and enforce_resolution:
            raise APIKeyInvalidError("API key does not match an active consumer")

        return consumer

    async def _resolve_consumer_by_client_credentials(
        self,
        context,
        client_id,
        secret_id,
        enforce_resolution,
    ):
        tenant_id = context.route.get("tenant_id") or context.tenant
        if not tenant_id:
            if enforce_resolution:
                raise APIKeyInvalidError("Tenant is required to resolve consumer")
            return None

        consumer = await self._consumers_collection.find_one(
            {
                "tenant_id": tenant_id,
                "client_id": client_id,
                "secret_id": secret_id,
                "status": {"$ne": "inactive"},
            }
        )

        if not consumer and enforce_resolution:
            raise APIKeyInvalidError("client_id/secret_id do not match an active consumer")

        return consumer

    async def before_request(self, context):
        config = self._plugin_config(context)
        header_name = str(config.get("header_name", "x-api-key")).lower()
        query_param = str(config.get("query_param", "api_key"))
        allow_client_credentials = bool(config.get("allow_client_credentials", False))
        client_id_header = str(config.get("client_id_header", "x-client-id")).lower()
        secret_id_header = str(config.get("secret_id_header", "x-secret-id")).lower()
        resolve_consumer = bool(config.get("resolve_consumer", True))
        enforce_consumer_resolution = bool(config.get("enforce_consumer_resolution", True))

        headers = self._headers_map(context)
        query = self._query_map(context)

        api_key = headers.get(header_name)
        if not api_key:
            values = query.get(query_param, [])
            api_key = values[0] if values else None

        client_id = headers.get(client_id_header)
        secret_id = headers.get(secret_id_header)

        if not api_key and not (allow_client_credentials and client_id and secret_id):
            raise APIKeyMissingError()

        if api_key:
            allowed_keys = self._configured_keys(config)
            if allowed_keys and api_key not in allowed_keys:
                raise APIKeyInvalidError()

        if resolve_consumer:
            consumer = None
            if api_key:
                consumer = await self._resolve_consumer(context, api_key, enforce_consumer_resolution)
            elif allow_client_credentials and client_id and secret_id:
                consumer = await self._resolve_consumer_by_client_credentials(
                    context,
                    client_id,
                    secret_id,
                    enforce_consumer_resolution,
                )

            if consumer:
                context.extra["consumer_id"] = consumer.get("_id")
                context.extra["consumer_name"] = consumer.get("name")
                context.extra["consumer_tags"] = consumer.get("tags") or []
                context.extra["consumer_actor_type"] = consumer.get("actor_type")
                context.extra["consumer_status"] = consumer.get("status")
                context.extra["consumer_plan_override"] = consumer.get("plan_override")
                context.extra["consumer_client_id"] = consumer.get("client_id")

        context.extra["api_key_authenticated"] = True