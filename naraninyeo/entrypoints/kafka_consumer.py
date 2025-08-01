"""
Kafka 메시지 처리 진입점
얇은 인터페이스 계층 - 메시지를 받아서 서비스로 위임만 함
"""
from opentelemetry import trace
import json
import loguru
import anyio
from aiokafka import AIOKafkaConsumer

from naraninyeo.core.config import Settings
from naraninyeo.di import container
from naraninyeo.adapters.clients import APIClient
from naraninyeo.services.conversation_service import ConversationService
from naraninyeo.services.message_parser import parse_message

tracer = trace.get_tracer(__name__)

async def main():
    """Kafka 컨슈머 메인 함수"""
    settings = await container.get(Settings)

    # 서비스 가져오기
    conversation_service = await container.get(ConversationService)
    api_client = await container.get(APIClient)

    # Kafka 컨슈머 설정
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=False
    )
    
    loguru.logger.info(f"Starting consumer for topic: {settings.KAFKA_TOPIC}")
    await consumer.start()
    
    try:
        async for msg in consumer:
            await process_message(msg, conversation_service, api_client)
            await consumer.commit()
    finally:
        await shutdown(consumer)

async def process_message(msg, conversation_service: ConversationService, api_client: APIClient):
    """단일 메시지 처리 - 에러 처리 분리"""
    try:
        with tracer.start_as_current_span("process_message") as span:
            # 1. 메시지 파싱
            message_string = msg.value.decode("utf-8")
            loguru.logger.info(f"Received message: {message_string}")
            span.set_attribute("message", message_string)
            
            value = json.loads(message_string)
            message = await parse_message(value)
            
            # 2. 메시지 처리 (저장 + 응답 생성) - 서비스에 위임
            async for response in conversation_service.process_message(message):
                loguru.logger.info(f"Sending response: {response.content.text}")
                await api_client.send_response(response)
                    
    except json.JSONDecodeError as e:
        loguru.logger.error(f"Invalid JSON message: {e}")
    except Exception as e:
        loguru.logger.error(f"Error processing message: {e}")
        # 필요하면 여기서 데드레터큐로 보내기

async def shutdown(consumer):
    """정리 작업"""
    loguru.logger.info("Consumer stopped")
    # Dishka 컨테이너 종료 (자동으로 데이터베이스 연결 등 리소스 정리)
    await container.close()
    loguru.logger.info("Resources cleaned up")

def run():
    """진입점 함수"""
    anyio.run(main)
