class PluginError(Exception):
    status_code = 400
    error_code = "PLUGIN_ERROR"
    description = "Plugin error"

    def __init__(self, description=None):
        if description:
            self.description = description
        super().__init__(self.description)

    def to_dict(self):
        return {
            "code": self.error_code,
            "description": self.description,
        }


class JWTMissingAuthHeaderError(PluginError):
    status_code = 401
    error_code = "JWT_MISSING_AUTH_HEADER"
    description = "Authorization header is missing or invalid"


class JWTInvalidScopeError(PluginError):
    status_code = 403
    error_code = "JWT_INVALID_SCOPE"
    description = "JWT token does not have the required scope"


class JWTInvalidTokenError(PluginError):
    status_code = 401
    error_code = "JWT_INVALID_TOKEN"
    description = "JWT token is invalid or expired"


class JWTMissingTenantError(PluginError):
    status_code = 403
    error_code = "JWT_MISSING_TENANT"
    description = "tenant_id was not found in token payload"


class RateLimitExceededError(PluginError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    description = "Request rate limit exceeded"


class CacheBackendUnavailableError(PluginError):
    status_code = 503
    error_code = "CACHE_BACKEND_UNAVAILABLE"
    description = "Cache backend is unavailable"