import os
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor

ENABLE_TELEMETRY = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() != ""

if ENABLE_TELEMETRY:
    resource = Resource.create({})

    trace.set_tracer_provider(TracerProvider(resource=resource))
    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.get_tracer_provider().add_span_processor(OpenInferenceSpanProcessor())

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter()
    )

    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[reader],
        )
    )
