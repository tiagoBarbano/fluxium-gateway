import ipaddress

from .base import BasePlugin
from .errors import IPRestrictionForbiddenError


class IPRestrictionPlugin(BasePlugin):
    name = "ip_restriction"
    order = 3

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

    def _resolve_ip(self, context, config):
        source = str(config.get("source", "client")).lower()
        if source == "x-forwarded-for":
            headers = self._headers_map(context)
            xff = headers.get("x-forwarded-for", "")
            if xff:
                return xff.split(",", 1)[0].strip()

        client = context.scope.get("client") or ()
        if len(client) >= 1:
            return str(client[0])
        return ""

    def _parse_networks(self, values):
        networks = []
        for value in values or []:
            candidate = str(value).strip()
            if not candidate:
                continue
            try:
                if "/" in candidate:
                    networks.append(ipaddress.ip_network(candidate, strict=False))
                else:
                    addr = ipaddress.ip_address(candidate)
                    prefix = 32 if addr.version == 4 else 128
                    networks.append(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))
            except ValueError:
                continue
        return networks

    def _is_match(self, ip_text, networks):
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError:
            return False
        return any(ip_obj in network for network in networks)

    async def before_request(self, context):
        config = self._plugin_config(context)
        ip_text = self._resolve_ip(context, config)
        if not ip_text:
            raise IPRestrictionForbiddenError("Could not resolve client IP")

        deny_networks = self._parse_networks(config.get("denylist", []))
        if deny_networks and self._is_match(ip_text, deny_networks):
            raise IPRestrictionForbiddenError(f"IP {ip_text} is denied")

        allow_networks = self._parse_networks(config.get("allowlist", []))
        if allow_networks and not self._is_match(ip_text, allow_networks):
            raise IPRestrictionForbiddenError(f"IP {ip_text} is not in allowlist")
