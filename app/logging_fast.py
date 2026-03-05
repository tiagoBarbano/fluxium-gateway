import sys
import orjson
from datetime import datetime
from opentelemetry import trace


def _current_trace_fields():
    span = trace.get_current_span()
    if span is None:
        return {"trace_id": None}

    span_context = span.get_span_context()
    if not span_context or not span_context.is_valid:
        return {"trace_id": None}

    return {
        "trace_id": f"{span_context.trace_id:032x}",
    }

def log_json(level, message, **extra):
    record = {
        "level": level,
        "message": message,
        "time": datetime.utcnow().isoformat(),
        **_current_trace_fields(),
        **extra,
    }
    sys.stdout.buffer.write(orjson.dumps(record) + b"\n")