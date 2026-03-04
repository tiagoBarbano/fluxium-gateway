from operator import itemgetter

from app.logging_fast import log_json


class PluginEngine:

    def __init__(self, plugins):
        self.plugins: dict = plugins

    def _normalized_plugins(self, context):
        plugin_input = context.route.get("plugins", [])
        normalized = []

        for position, p_input in enumerate(plugin_input):
            if isinstance(p_input, dict):
                plugin_type = p_input.get("type")
                if not plugin_type:
                    continue
                normalized.append(
                    {
                        "type": plugin_type,
                        "order": int(p_input.get("order", position + 1)),
                        "config": p_input.get("config", {}),
                    }
                )
                continue

            if isinstance(p_input, str):
                normalized.append(
                    {
                        "type": p_input,
                        "order": position + 1,
                        "config": {},
                    }
                )

        return normalized

    def _get_plugin(self, context, plugin_type):
        plugin = self.plugins.get(plugin_type)
        if plugin is None:
            log_json(
                "ERROR",
                "plugin_not_found",
                route=context.route["prefix"],
                plugin_type=plugin_type,
            )
        return plugin

    async def run_before(self, context):
        plugins_to_run = sorted(
            (p for p in self._normalized_plugins(context) if p["order"] != 0),
            key=itemgetter("order")
        )

        for p_input in plugins_to_run:
            log_json(
                "DEBUG",
                "plugin_before_request",
                route=context.route["prefix"],
                plugin_type=p_input["type"],
            )
            plugin = self._get_plugin(context, p_input["type"])
            if plugin is None:
                continue
            if getattr(plugin, "phase", "before_after") != "before_after":
                continue
            await plugin.before_request(context)

    async def run_after(self, context):
        plugins_to_run = sorted(
            (p for p in self._normalized_plugins(context) if p["order"] != 0),
            key=itemgetter("order")
        )
        
        for p_input in reversed(plugins_to_run):
            log_json(
                "DEBUG",
                "plugin_after_response",
                route=context.route["prefix"],
                plugin_type=p_input["type"],
            )
            plugin = self._get_plugin(context, p_input["type"])
            if plugin is None:
                continue
            if getattr(plugin, "phase", "before_after") != "before_after":
                continue
            await plugin.after_response(context)

    async def run_forward(self, context, call_upstream):
        plugins_to_run = sorted(self._normalized_plugins(context), key=itemgetter("order"))

        forward_plugins = []
        for p_input in plugins_to_run:
            plugin = self._get_plugin(context, p_input["type"])
            if plugin is None:
                continue
            if getattr(plugin, "phase", "before_after") != "forward":
                continue
            forward_plugins.append((plugin, p_input.get("config", {})))

        async def execute(index):
            if index >= len(forward_plugins):
                return await call_upstream()

            plugin, config = forward_plugins[index]

            async def call_next():
                return await execute(index + 1)

            log_json(
                "DEBUG",
                "plugin_around_request",
                route=context.route["prefix"],
                plugin_type=plugin.name,
            )
            return await plugin.around_request(context, call_next, config)

        return await execute(0)
 