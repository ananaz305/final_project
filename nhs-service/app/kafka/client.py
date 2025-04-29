import asyncio
import json
import logging
from typing import Optional, List, Callable, Any, Dict, Coroutine
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

producer: Optional[AIOKafkaProducer] = None
consumers: List[AIOKafkaConsumer] = []
consumer_tasks: List[asyncio.Task] = []

def get_kafka_producer() -> AIOKafkaProducer:
    if producer is None:
        raise RuntimeError("Kafka producer is not initialized")
    return producer

async def connect_kafka_producer():
    global producer
    client_id = settings.KAFKA_CLIENT_ID
    logger.info(f"[{client_id}] Connecting Kafka producer to {settings.KAFKA_BROKER_URL}...")
    retry_delay = 5
    while producer is None:
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                client_id=client_id,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all'
            )
            await producer.start()
            logger.info(f"[{client_id}] Kafka producer connected successfully.")
            return producer
        except KafkaConnectionError as e:
            logger.error(f"[{client_id}] Failed to connect Kafka producer: {e}. Retrying in {retry_delay} seconds...")
            producer = None
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"[{client_id}] An unexpected error occurred during Kafka producer connection: {e}")
            producer = None
            await asyncio.sleep(retry_delay)

async def disconnect_kafka_producer():
    global producer
    client_id = settings.KAFKA_CLIENT_ID
    if producer:
        logger.info(f"[{client_id}] Disconnecting Kafka producer...")
        try:
            await producer.stop()
            producer = None
            logger.info(f"[{client_id}] Kafka producer disconnected successfully.")
        except Exception as e:
            logger.error(f"[{client_id}] Error disconnecting Kafka producer: {e}")

async def send_kafka_message(topic: str, message: Dict[str, Any]):
    global producer
    client_id = settings.KAFKA_CLIENT_ID
    if not producer:
        logger.error(f"[{client_id}] Failed to send message to {topic}: Producer unavailable.")
        return
    try:
        logger.debug(f"[{client_id}] Sending message to Kafka topic {topic}: {message}")
        await producer.send_and_wait(topic, value=message)
        logger.debug(f"[{client_id}] Message successfully sent to topic {topic}")
    except KafkaConnectionError as e:
        logger.error(f"[{client_id}] Connection error sending message to topic {topic}: {e}")
        producer = None
        asyncio.create_task(connect_kafka_producer())
    except Exception as e:
        logger.error(f"[{client_id}] Failed to send message to topic {topic}: {e}")

async def start_kafka_consumer(
        topic: str,
        group_id: str,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
):
    client_id = settings.KAFKA_CLIENT_ID
    logger.info(f"[{client_id}] Starting Kafka consumer for topic '{topic}' with group_id '{group_id}'...")
    consumer = None
    retry_delay = 5
    while True:
        try:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                group_id=group_id,
                client_id=f"{client_id}-{group_id}",
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True,
            )
            await consumer.start()
            consumers.append(consumer)
            logger.info(f"[{client_id}] Kafka consumer for topic '{topic}' (group: {group_id}) started successfully.")

            async for msg in consumer:
                logger.debug(f"[{client_id}] Received message: topic={msg.topic}, partition={msg.partition}, offset={msg.offset}")
                try:
                    await handler(msg.value)
                except Exception as e:
                    logger.error(f"[{client_id}] Error processing message from topic {topic} in group {group_id}: {e}", exc_info=True)

        except KafkaConnectionError as e:
            logger.error(f"[{client_id}] Connection error for consumer topic '{topic}' (group: {group_id}): {e}. Retrying in {retry_delay} seconds...")
            if consumer:
                try:
                    await consumer.stop()
                    if consumer in consumers: consumers.remove(consumer)
                except: pass
            consumer = None
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"[{client_id}] Unexpected error in consumer for topic '{topic}' (group: {group_id}): {e}. Retrying in {retry_delay} seconds...", exc_info=True)
            if consumer:
                try:
                    await consumer.stop()
                    if consumer in consumers: consumers.remove(consumer)
                except: pass
            consumer = None
            await asyncio.sleep(retry_delay)

async def disconnect_kafka_consumers():
    client_id = settings.KAFKA_CLIENT_ID
    logger.info(f"[{client_id}] Disconnecting {len(consumers)} Kafka consumer(s)...")
    for task in consumer_tasks:
        if not task.done():
            task.cancel()
    if consumer_tasks:
        results = await asyncio.gather(*consumer_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"Consumer task {i+1} cancelled successfully.")
            elif isinstance(result, Exception):
                logger.error(f"Error during consumer task {i+1} cancellation/shutdown: {result}")

    stopped_count = 0
    for consumer in list(consumers):
        try:
            await consumer.stop()
            if consumer in consumers: consumers.remove(consumer)
            stopped_count += 1
        except Exception as e:
            logger.error(f"[{client_id}] Error stopping consumer {consumer}: {e}")
    logger.info(f"[{client_id}] Successfully disconnected {stopped_count} Kafka consumer(s).")
    consumer_tasks.clear()

def create_consumer_task(topic: str, group_id: str, handler: Callable) -> asyncio.Task:
    task = asyncio.create_task(start_kafka_consumer(topic, group_id, handler))
    consumer_tasks.append(task)
    return task