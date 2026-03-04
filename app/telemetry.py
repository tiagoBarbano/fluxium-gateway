import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

otel_url = os.getenv(
	"OTEL_EXPORTER_OTLP_ENDPOINT",
	"http://localhost:4317",
)


class ErrorAwareSampler(sampling.Sampler):
    """Sampler that respects the force_sample attribute in attributes."""

    def __init__(self, ratio: str):
        self.normal_sampler = sampling.TraceIdRatioBased(ratio)

    def should_sample(self, parent_context, trace_id, name, kind, attributes, links):
        # if attributes and attributes.get("force_sample") is True:
        #     return sampling.SamplingResult(sampling.Decision.RECORD_AND_SAMPLE)
        return self.normal_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links
        )

    def get_description(self):
        return f"ErrorAwareSampler({self.normal_sampler.get_description()})"


"""Responsável por habilitar o OpenTelemetry para o Tracing"""

exporter = OTLPSpanExporter(endpoint=otel_url, insecure=True)

resource = Resource.create(attributes={"service.name": "fluxium-gateway"})
tracer = TracerProvider(resource=resource)
tracer.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(tracer)

