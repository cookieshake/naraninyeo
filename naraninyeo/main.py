from opentelemetry import trace

from naraninyeo.core.config import settings
from naraninyeo.core.database import mc
from naraninyeo.models.message import Message
from naraninyeo.services.message_handler import handle_message
from naraninyeo.services.message_parser import parse_message
from naraninyeo.services.api_client import send_response
import json
import loguru

import anyio
from aiokafka import AIOKafkaConsumer

tracer = trace.get_tracer(__name__)

async def main():
    await mc.connect_to_database()
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
            try:
                with tracer.start_as_current_span("process_message"):
                    value = json.loads(msg.value.decode("utf-8"))
                    loguru.logger.info(f"Received message: {value}")
                    message = await parse_message(value)
                    async for r in handle_message(message):
                        loguru.logger.info(f"Sending response: {r.content.text}")
                        await send_response(r)
                    await consumer.commit()
            except Exception as e:
                loguru.logger.error(f"Error processing message: {e}")
    finally:
        loguru.logger.info("Stopping consumer")
        await consumer.stop()
        loguru.logger.info("Consumer stopped")
        loguru.logger.info("Closing database connection")
        await mc.close_database_connection()

if __name__ == "__main__":
    anyio.run(main)