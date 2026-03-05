import orjson
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from app.logging_fast import log_json


def test_log_json_includes_empty_trace_fields_without_active_span(capfd):
    log_json("INFO", "hello")

    out, _ = capfd.readouterr()
    record = orjson.loads(out.strip())

    assert record["trace_id"] is None
    assert record["span_id"] is None


def test_log_json_includes_trace_and_span_ids_from_active_span(capfd):
    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    span = NonRecordingSpan(span_context)

    with trace.use_span(span, end_on_exit=False):
        log_json("INFO", "hello")

    out, _ = capfd.readouterr()
    record = orjson.loads(out.strip())

    assert record["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert record["span_id"] == "1234567890abcdef"