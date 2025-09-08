import asyncio
import logging
import os
import sys
from typing import Any, cast

import opentelemetry._logs as otel_logs  # type: ignore[reportPrivateImportUsage]
import opentelemetry.exporter.otlp.proto.http._log_exporter as otlp_log_exporter  # type: ignore[reportPrivateImportUsage]
import opentelemetry.sdk._logs as otel_sdk_logs  # type: ignore[reportPrivateImportUsage]
import opentelemetry.sdk._logs.export as otel_sdk_logs_export  # type: ignore[reportPrivateImportUsage]
from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
from openinference.semconv.resource import ResourceAttributes
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# So pyright doesn't flag private modules; treat as dynamic at type-check time
otel_logs = cast(Any, otel_logs)
otlp_log_exporter = cast(Any, otlp_log_exporter)
otel_sdk_logs = cast(Any, otel_sdk_logs)
otel_sdk_logs_export = cast(Any, otel_sdk_logs_export)

ENABLE_OTLP_EXPORTER = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() != ""

if __name__ == "__main__":

    def pretty_span(span: ReadableSpan) -> str:
        name = span.name
        status = span.status
        code = status.status_code.name if status and getattr(status, "status_code", None) else None

        duration_ms = None
        start_time = getattr(span, "start_time", None)
        end_time = getattr(span, "end_time", None)
        if isinstance(start_time, int) and isinstance(end_time, int):
            try:
                duration_ms = int(round((end_time - start_time) / 1e6))
            except Exception:
                duration_ms = None

        parts: list[str] = [name]
        if code:
            parts.append(code)
        if duration_ms is not None:
            parts.append(f"{duration_ms}ms")
        return " ".join(parts) + "\n"

    def tiny_log(record: Any) -> str:
        # level = (
        #     record.severity_text
        #     if record.severity_text
        #     else (str(record.severity_number) if record.severity_number is not None else None)
        # )
        body = record.body
        if not isinstance(body, str):
            body = str(body)
        # Collapse whitespace/newlines to keep one-liners short
        body = " ".join(body.split())

        logger_name = None
        try:
            attrs = record.attributes or {}
            logger_name = (
                attrs.get("logger.name")
                or attrs.get("logger")
                or attrs.get("otel.logger_name")
                or attrs.get("otel.library.name")
            )
        except Exception:
            logger_name = None

        parts: list[str] = []
        # if level:
        #     parts.append(level)
        if logger_name:
            parts.append(f"{logger_name}:")
        parts.append(body)
        return " ".join(parts) + "\n"

    resource = Resource.create({ResourceAttributes.PROJECT_NAME: "naraninyeo"})

    # TRACES
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(OpenInferenceSpanProcessor())
    if ENABLE_OTLP_EXPORTER:
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(formatter=pretty_span)))
    trace.set_tracer_provider(tracer_provider)

    # METRICS
    if ENABLE_OTLP_EXPORTER:
        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[metric_reader],
            )
        )

    # LOGS
    logger_provider = otel_sdk_logs.LoggerProvider()
    if ENABLE_OTLP_EXPORTER:
        logger_provider.add_log_record_processor(
            otel_sdk_logs_export.BatchLogRecordProcessor(otlp_log_exporter.OTLPLogExporter())
        )
    logger_provider.add_log_record_processor(
        otel_sdk_logs_export.BatchLogRecordProcessor(otel_sdk_logs_export.ConsoleLogExporter(formatter=tiny_log))
    )
    otel_logs.set_logger_provider(logger_provider)

    logging_handler = otel_sdk_logs.LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.basicConfig(handlers=[logging_handler], level=logging.INFO)

    # INSTRUMENTATION
    HTTPXClientInstrumentor().instrument()
    PymongoInstrumentor().instrument()

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    match arg:
        case "cli":
            from naraninyeo.entrypoints.cli import main

            asyncio.run(main())
        case "kafka":
            from naraninyeo.entrypoints.kafka import main

            asyncio.run(main())
        case "http":
            from naraninyeo.entrypoints.http import main

            main()
        case _:
            raise ValueError(f"Unknown entrypoint: {arg}. Use 'cli' or 'kafka'.")
