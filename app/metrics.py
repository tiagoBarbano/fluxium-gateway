from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total requests",
    ["method", "route", "status", "tenant"]
)

REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Request latency",
    ["method", "route", "tenant"]
)

IGNORED_PATHS = {"/metrics", "/docs", "/openapi.json", "/favicon.ico"}

def prometheus_metrics():
    """Generate Prometheus metrics for the application."""
    return generate_latest()
