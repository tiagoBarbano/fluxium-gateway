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


class ValidationFailedError(PluginError):
    status_code = 400
    error_code = "VALIDATION_FAILED"
    description = "Request validation failed"


class ValidationInvalidJsonError(PluginError):
    status_code = 400
    error_code = "VALIDATION_INVALID_JSON"
    description = "Request body must be valid JSON"


class TransformationInvalidJsonError(PluginError):
    status_code = 400
    error_code = "TRANSFORMATION_INVALID_JSON"
    description = "Transformation requires valid JSON body"


class EventBridgePublishError(PluginError):
    status_code = 502
    error_code = "EVENT_BRIDGE_PUBLISH_ERROR"
    description = "Failed to publish event"


class APIKeyMissingError(PluginError):
    status_code = 401
    error_code = "API_KEY_MISSING"
    description = "API key is missing"


class APIKeyInvalidError(PluginError):
    status_code = 403
    error_code = "API_KEY_INVALID"
    description = "API key is invalid"


class CORSOriginNotAllowedError(PluginError):
    status_code = 403
    error_code = "CORS_ORIGIN_NOT_ALLOWED"
    description = "Origin is not allowed"


class IPRestrictionForbiddenError(PluginError):
    status_code = 403
    error_code = "IP_RESTRICTION_FORBIDDEN"
    description = "Request IP is not allowed"


class RequestSizeExceededError(PluginError):
    status_code = 413
    error_code = "REQUEST_SIZE_EXCEEDED"
    description = "Request payload is too large"


class ConsumerNotResolvedError(PluginError):
    status_code = 401
    error_code = "CONSUMER_NOT_RESOLVED"
    description = "Consumer was not resolved for this request"


class ConsumerACLForbiddenError(PluginError):
    status_code = 403
    error_code = "CONSUMER_ACL_FORBIDDEN"
    description = "Consumer is not allowed to access this route"