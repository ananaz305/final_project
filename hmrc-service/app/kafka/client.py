# Копируем содержимое из nns-service/app/kafka/client.py,
# так как структура клиента идентична, и только KAFKA_CLIENT_ID
# будет отличаться (он берется из settings)

import asyncio
import json
import logging
from typing import Optional, List, Callable, Any, Dict, Coroutine
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

# Важно: Импортируем settings из правильного места!
from app.core.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

producer: Optional[AIOKafkaProducer] = None
consumer: Optional[AIOKafkaConsumer] = None # Один consumer для этого сервиса
consumer_task: Optional[asyncio.Task] = None

def get_kafka_producer() -> AIOKafkaProducer:
    if producer is None:
        raise RuntimeError("Kafka producer is not initialized")
    return producer

async def connect_kafka_producer():
    global producer
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Connecting Kafka producer to {settings.KAFKA_BROKER_URL}...")
    retry_delay = 5
    while producer is None:
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                client_id=settings.KAFKA_CLIENT_ID,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all'
            )
            await producer.start()
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Kafka producer connected successfully.")
            return producer
        except KafkaConnectionError as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Failed to connect Kafka producer: {e}. Retrying in {retry_delay} seconds...")
            producer = None
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] An unexpected error occurred during Kafka producer connection: {e}")
            producer = None
            await asyncio.sleep(retry_delay)

async def disconnect_kafka_producer():
    global producer
    if producer:
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Disconnecting Kafka producer...")
        try:
            await producer.stop()
            producer = None
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Kafka producer disconnected successfully.")
        except Exception as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error disconnecting Kafka producer: {e}")

async def send_kafka_message(topic: str, message: Dict[str, Any]):
    global producer
    if not producer:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Failed to send message to {topic}: Producer unavailable.")
        return
    try:
        logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Sending message to Kafka topic {topic}: {message}")
        await producer.send_and_wait(topic, value=message)
        logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Message successfully sent to topic {topic}")
    except KafkaConnectionError as e:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Connection error sending message to topic {topic}: {e}")
        producer = None
        asyncio.create_task(connect_kafka_producer())
    except Exception as e:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Failed to send message to topic {topic}: {e}")

async def start_kafka_consumer(
        topic: str,
        group_id: str,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
):
    global consumer, consumer_task
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Starting Kafka consumer for topic '{topic}' with group_id '{group_id}'...")
    retry_delay = 5
    while True:
        try:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                group_id=group_id,
                client_id=f"{settings.KAFKA_CLIENT_ID}-{group_id}",
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True,
            )
            await consumer.start()
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Kafka consumer for topic '{topic}' started successfully.")

            async for msg in consumer:
                logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Received message: topic={msg.topic}, partition={msg.partition}, offset={msg.offset}")
                try:
                    await handler(msg.value)
                except Exception as e:
                    logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error processing message from topic {topic}: {e}", exc_info=True)

        except KafkaConnectionError as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Connection error for consumer topic '{topic}': {e}. Retrying in {retry_delay} seconds...")
            if consumer:
                await consumer.stop()
            consumer = None
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Unexpected error in consumer for topic '{topic}': {e}. Retrying in {retry_delay} seconds...", exc_info=True)
            if consumer:
                await consumer.stop()
            consumer = None
            await asyncio.sleep(retry_delay)
        finally:
            if consumer:
                try:
                    await consumer.stop()
                except Exception as e:
                    logger.error(f"Error stopping consumer for topic {topic} in finally block: {e}")
            consumer = None

async def disconnect_kafka_consumer():
    global consumer, consumer_task
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Disconnecting Kafka consumer...")
    if consumer_task and not consumer_task.done():
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Consumer task cancelled.")
        except Exception as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error during consumer task cancellation: {e}")

    if consumer:
        try:
            await consumer.stop()
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Kafka consumer stopped.")
        except Exception as e:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error stopping Kafka consumer: {e}")
    consumer = None
    consumer_task = None

def create_consumer_task(topic: str, group_id: str, handler: Callable) -> asyncio.Task:
    global consumer_task
    if consumer_task is not None:
        logger.warning(f"[{settings.KAFKA_CLIENT_ID}] Consumer task already exists. Cannot create another.")
        return consumer_task
    consumer_task = asyncio.create_task(start_kafka_consumer(topic, group_id, handler))
    return consumer_task