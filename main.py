import asyncio
import logging
import sys

from opentelemetry import metrics, trace, _logs
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from openinference.semconv.resource import ResourceAttributes
from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor

if __name__ == "__main__":
    resource = Resource.create({
        ResourceAttributes.PROJECT_NAME: "naraninyeo"
    })

    # TRACES
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(OpenInferenceSpanProcessor())
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # METRICS
    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
    )

    # LOGS
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))
    _logs.set_logger_provider(logger_provider)

    logging_handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
    logging.basicConfig(handlers=[logging_handler], level=logging.DEBUG)

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    match arg:
        case "cli":
            from naraninyeo.entrypoints.cli import main
            asyncio.run(main())
        case "kafka":
            from naraninyeo.entrypoints.kafka import main
            asyncio.run(main())
        case _:
            raise ValueError(f"Unknown entrypoint: {arg}. Use 'cli' or 'kafka'.")