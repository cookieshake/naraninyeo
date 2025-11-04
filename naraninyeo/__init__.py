"""Public entrypoints for the NaraninYeo assistant runtime."""

from dotenv import load_dotenv

load_dotenv()

from naraninyeo.api.infrastructure.util.opentelemetry import (  # noqa: E402
    OpenTelemetryInstrumentation,
    OpenTelemetryLog,
    OpenTelemetryMetrics,
    OpenTelemetryTracer,
)

OpenTelemetryLog().configure()
OpenTelemetryTracer().configure()
OpenTelemetryMetrics().configure()
OpenTelemetryInstrumentation().configure()
