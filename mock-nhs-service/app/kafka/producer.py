import json
import logging
from aiokafka import AIOKafkaProducer
from ..core.config import KAFKA_BOOTSTRAP_SERVERS, NHS_RESPONSE_TOPIC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

producer = None

async def get_kafka_producer():
    global producer
    if producer is None:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await producer.start()
        logger.info("Kafka producer started.")
    return producer

async def send_nhs_response(message: dict, topic: str = NHS_RESPONSE_TOPIC, key: str = None):
    kafka_producer = await get_kafka_producer()
    try:
        logger.info(f"Sending message: {message} to topic: {topic}")
        if key:
            await kafka_producer.send_and_wait(topic, value=message, key=key.encode('utf-8'))
        else:
            await kafka_producer.send_and_wait(topic, value=message)
        logger.info("Message sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        # Здесь может быть логика повторной отправки или обработки ошибок

async def stop_kafka_producer():
    global producer
    if producer:
        await producer.stop()
        producer = None
        logger.info("Kafka producer stopped.")

# Рекомендуется вызывать stop_kafka_producer() при завершении работы приложения,
# например, в событии shutdown FastAPI.
# В main.py:
# @app.on_event("shutdown")
# async def shutdown_event():
#     logger.info("Shutting down Mock NHS Service...")
#     await stop_kafka_producer() # Добавить эту строку 