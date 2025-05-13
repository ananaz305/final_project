import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer
from ..core.config import KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC, MOCK_NHS_SIMULATE_DELAY_SECONDS
from .handlers import handle_nhs_request # Мы создадим этот файл позже

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def consume_nhs_requests(bootstrap_servers: str, topic: str):
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id="nhs_mock_service_group", # Уникальный group_id для consumer'а
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset="earliest" # Начинать читать с самого раннего сообщения, если нет сохраненного offset
    )
    await consumer.start()
    logger.info(f"Consumer started for topic: {topic}")
    try:
        async for msg in consumer:
            logger.info(f"Received message: {msg.value} from topic {msg.topic} partition {msg.partition} offset {msg.offset}")
            try:
                request_data = msg.value
                # Имитация задержки обработки
                await asyncio.sleep(MOCK_NHS_SIMULATE_DELAY_SECONDS)

                # Передача данных в обработчик
                await handle_nhs_request(request_data)

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON message: {msg.value}")
            except Exception as e:
                logger.error(f"Error processing message: {msg.value}, error: {e}")
            # В реальном приложении здесь также может быть логика для отправки сообщения в DLQ (Dead Letter Queue)
            # или подтверждения обработки сообщения (commit offset), в зависимости от настроек consumer'а
    finally:
        logger.info("Stopping consumer...")
        await consumer.stop()
        logger.info("Consumer stopped.")

if __name__ == '__main__':
    # Это для возможности запуска consumer'а отдельно для тестирования
    async def main():
        await consume_nhs_requests(KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC)

    asyncio.run(main()) 