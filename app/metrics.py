from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "gateway_requests_total",
    "Total requests",
    ["method", "route", "status", "tenant"]
)

REQUEST_LATENCY = Histogram(
    "gateway_request_latency_seconds",
    "Request latency",
    ["route", "tenant"]
)

IGNORED_PATHS = {"/metrics", "/docs", "/openapi.json", "/favicon.ico"}

def prometheus_metrics():
    """Generate Prometheus metrics for the application."""
    return generate_latest()
