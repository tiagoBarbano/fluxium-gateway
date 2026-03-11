from .base import BasePlugin
from .errors import ConsumerACLForbiddenError, ConsumerNotResolvedError
from app.config_store import db


class ConsumerACLPlugin(BasePlugin):
    name = "consumer_acl"
    order = 5

    @property
    def _permissions_collection(self):
        return db.consumer_permissions

    def _plugin_config(self, context):
        for plugin in context.route.get("plugins", []):
            if isinstance(plugin, dict) and plugin.get("type") == self.name:
                return plugin.get("config", {})
        return {}

    async def _is_route_allowed_by_permission(self, context, consumer_id):
        tenant_id = context.route.get("tenant_id") or context.tenant
        if not tenant_id:
            return False

        method = str(context.scope.get("method", "GET")).upper()
        route_id = context.route.get("_id")
        api_id = context.route.get("api_id")

        cursor = self._permissions_collection.find(
            {
                "tenant_id": tenant_id,
                "consumer_id": consumer_id,
                "status": {"$ne": "inactive"},
            }
        )

        async for permission in cursor:
            permission_route_id = permission.get("route_id")
            permission_api_id = permission.get("api_id")
            permission_methods = [str(item).upper() for item in (permission.get("methods") or ["*"])]

            if permission_route_id and permission_route_id != route_id:
                continue
            if permission_api_id and permission_api_id != api_id:
                continue
            if "*" not in permission_methods and method not in permission_methods:
                continue

            return True

        return False

    async def before_request(self, context):
        config = self._plugin_config(context)

        consumer_id = context.extra.get("consumer_id")
        consumer_tags = set(context.extra.get("consumer_tags") or [])
        consumer_actor_type = context.extra.get("consumer_actor_type")

        allow_anonymous = bool(config.get("allow_anonymous", False))
        if not consumer_id and not allow_anonymous:
            raise ConsumerNotResolvedError()

        deny_consumer_ids = set(config.get("deny_consumer_ids") or [])
        if consumer_id and consumer_id in deny_consumer_ids:
            raise ConsumerACLForbiddenError("Consumer explicitly denied")

        allow_consumer_ids = set(config.get("allow_consumer_ids") or [])
        if allow_consumer_ids and consumer_id not in allow_consumer_ids:
            raise ConsumerACLForbiddenError("Consumer is not in allow list")

        deny_tags = set(config.get("deny_tags") or [])
        if consumer_tags.intersection(deny_tags):
            raise ConsumerACLForbiddenError("Consumer tag is denied")

        allow_tags = set(config.get("allow_tags") or [])
        if allow_tags and not consumer_tags.intersection(allow_tags):
            raise ConsumerACLForbiddenError("Consumer does not have required tags")

        required_actor_types = set(config.get("required_actor_types") or [])
        if required_actor_types and consumer_actor_type not in required_actor_types:
            raise ConsumerACLForbiddenError("Consumer actor_type is not allowed")

        enforce_permissions = bool(config.get("enforce_permissions", True))
        if enforce_permissions and consumer_id:
            is_allowed = await self._is_route_allowed_by_permission(context, consumer_id)
            if not is_allowed:
                raise ConsumerACLForbiddenError("Consumer has no permission for this route")

        context.extra["consumer_acl_passed"] = True
