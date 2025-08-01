#!/usr/bin/env python
"""
나란잉여 애플리케이션의 통합 진입점 모듈
실행 방식에 따라 적절한 진입점을 호출합니다
"""

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


import argparse
from naraninyeo.entrypoints import kafka_consumer, cli_client

def main():
    """메인 진입점 함수"""
    parser = argparse.ArgumentParser(description="나란잉여 애플리케이션")
    
    # 서브 커맨드 설정
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령")
    
    # Kafka 컨슈머 명령 설정
    kafka_parser = subparsers.add_parser("kafka", help="Kafka 컨슈머로 실행")
    
    # CLI 클라이언트 명령 설정
    cli_parser = subparsers.add_parser("cli", help="로컬 CLI 클라이언트로 실행")
    
    # 인자 파싱
    args = parser.parse_args()
    
    # 명령에 따라 적절한 진입점 실행
    if args.command == "kafka":
        print("🚀 Kafka 컨슈머로 실행합니다...")
        kafka_consumer.run()
    elif args.command == "cli":
        print("🚀 로컬 CLI 클라이언트로 실행합니다...")
        cli_client.run()
    else:
        # 기본값은 CLI 클라이언트 (명령 없이 실행할 경우)
        print("🚀 기본 모드: 로컬 CLI 클라이언트로 실행합니다...")
        cli_client.run()

if __name__ == "__main__":
    main()
