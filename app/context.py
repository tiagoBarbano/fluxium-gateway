class RequestContext:
    def __init__(self, scope, route, tenant):
        self.scope = scope
        self.route = route
        self.tenant = tenant
        self.response = None
        self.extra = {}