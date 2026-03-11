import sys
import os
import orjson
from datetime import datetime
from opentelemetry import trace


_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def _configured_level_value():
    configured = os.getenv("GATEWAY_LOG_LEVEL", "INFO").upper()
    return _LEVELS.get(configured, _LEVELS["INFO"])


def _event_level_value(level: str):
    return _LEVELS.get((level or "").upper(), _LEVELS["INFO"])


def _current_trace_fields():
    span = trace.get_current_span()
    if span is None:
        return {"trace_id": None, "span_id": None}

    span_context = span.get_span_context()
    if not span_context or not span_context.is_valid:
        return {"trace_id": None, "span_id": None}

    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }

def log_json(level, message, **extra):
    if _event_level_value(level) < _configured_level_value():
        return

    record = {
        "level": level,
        "message": message,
        "time": datetime.utcnow().isoformat(),
        **_current_trace_fields(),
        **extra,
    }
    sys.stdout.buffer.write(orjson.dumps(record) + b"\n")