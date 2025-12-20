import logging
import os
from datetime import datetime

from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.aiokafka import AIOKafkaInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, ReadableLogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.semconv.attributes import service_attributes
from pydantic_ai import Agent

ENABLE_OTLP_EXPORTER = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() != ""

resource = Resource.create({service_attributes.SERVICE_NAME: "naraninyeo"})


class OpenTelemetryLog:
    def configure(self):
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            SimpleLogRecordProcessor(ConsoleLogExporter(formatter=self.log_formatter))
        )
        if ENABLE_OTLP_EXPORTER:
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        set_logger_provider(logger_provider)
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logging.basicConfig(handlers=[handler], level=logging.INFO)

    def log_formatter(self, readable_log_record: ReadableLogRecord) -> str:
        record = readable_log_record.log_record
        ts = datetime.fromtimestamp((record.timestamp or 1) / 1e9)
        att = record.attributes or {}
        filepath = att.get("code.file.path", "")
        if isinstance(filepath, str):
            filepath = filepath.split("/")[-1]
        lineno = att.get("code.line.number", 0)
        fname = att.get("code.function.name", "")
        return f"::LOG:: [{ts.strftime('%Y-%m-%d %H:%M:%S')}] ({filepath}:{lineno}:{fname}) {record.body}\n"


class OpenTelemetryTracer:
    def configure(self):
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(OpenInferenceSpanProcessor())
        tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(formatter=self.span_formatter)))
        if ENABLE_OTLP_EXPORTER:
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

    def span_formatter(self, span: ReadableSpan) -> str:
        if isinstance(span.end_time, int) and isinstance(span.start_time, int):
            duration_ms = int(round((span.end_time - span.start_time) / 1e6))
        else:
            duration_ms = 0
        ts = datetime.fromtimestamp((span.end_time or 1) / 1e9)
        return (
            f"::SPN:: "
            f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"({span.name}) "
            f"{span.status.status_code.name} "
            f"{duration_ms}ms"
            "\n"
        )


class OpenTelemetryMetrics:
    def configure(self):
        if ENABLE_OTLP_EXPORTER:
            metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            provider = MeterProvider(metric_readers=[metric_reader])
            metrics.set_meter_provider(
                meter_provider=provider,
            )


class OpenTelemetryInstrumentation:
    def configure(self):
        Agent.instrument_all()
        SystemMetricsInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        AIOKafkaInstrumentor().instrument()
        os.environ["LANGSMITH_OTEL_ENABLED"] = "true"
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_OTEL_ONLY"] = "true"
