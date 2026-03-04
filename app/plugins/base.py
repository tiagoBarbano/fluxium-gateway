class BasePlugin:
    name: str = None
    order: int = 0
    enabled_by_default: bool = False
    phase: str = "before_after"

    async def before_request(self, context):
        pass

    async def after_response(self, context):
        pass

    async def around_request(self, context, call_next, config):
        return await call_next()

    async def run_on_error(self, context, error):
        pass