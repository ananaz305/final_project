import asyncio
import json
import logging
from typing import Optional, List, Callable, Any, Dict
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
    logger.info(f"Connecting Kafka producer to {settings.KAFKA_BROKER_URL}...")
    retry_delay = 5
    while producer is None:
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                client_id=settings.KAFKA_CLIENT_ID,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all' # Гарантия доставки (можно изменить на 1 или 0)
            )
            await producer.start()
            logger.info("Kafka producer connected successfully.")
            return producer
        except KafkaConnectionError as e:
            logger.error(f"Failed to connect Kafka producer: {e}. Retrying in {retry_delay} seconds...")
            producer = None # Reset producer
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"An unexpected error occurred during Kafka producer connection: {e}")
            producer = None
            await asyncio.sleep(retry_delay)


async def disconnect_kafka_producer():
    global producer
    if producer:
        logger.info("Disconnecting Kafka producer...")
        try:
            await producer.stop()
            producer = None
            logger.info("Kafka producer disconnected successfully.")
        except Exception as e:
            logger.error(f"Error disconnecting Kafka producer: {e}")

async def send_kafka_message(topic: str, message: Dict[str, Any]):
    global producer
    if not producer:
        logger.warning(f"Kafka producer not available. Attempting to reconnect...")
        # Попытка переподключения может быть рискованной в обработчике запроса
        # Лучше иметь фоновый процесс для поддержания соединения
        # await connect_kafka_producer()
        # if not producer:
        #     logger.error(f"Failed to send message to {topic}: Producer unavailable.")
        #     return
        logger.error(f"Failed to send message to {topic}: Producer unavailable.")
        return # Не отправляем, если продюсер не готов

    try:
        logger.debug(f"Sending message to Kafka topic {topic}: {message}")
        await producer.send_and_wait(topic, value=message)
        logger.debug(f"Message successfully sent to topic {topic}")
    except KafkaConnectionError as e:
        logger.error(f"Connection error sending message to topic {topic}: {e}")
        # Попытка переподключения или обработка ошибки
        # Возможно, стоит сбросить producer и попытаться переподключиться в фоне
        producer = None # Считаем соединение потерянным
        connect_kafka_producer() # Запускаем попытку переподключения в фоне
    except Exception as e:
        logger.error(f"Failed to send message to topic {topic}: {e}")

async def start_kafka_consumer(
        topic: str,
        group_id: str,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
):
    """Starts a Kafka consumer for a specific topic and group_id."""
    logger.info(f"Starting Kafka consumer for topic '{topic}' with group_id '{group_id}'...")
    consumer = None
    retry_delay = 5
    while True: # Loop for reconnection attempts
        try:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                group_id=group_id,
                client_id=f"{settings.KAFKA_CLIENT_ID}-{group_id}", # More specific client ID
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='earliest', # Начать читать с начала, если нет offset'а
                enable_auto_commit=True, # Автокоммит offset'ов
                # auto_commit_interval_ms=5000 # Интервал автокоммита
            )
            await consumer.start()
            consumers.append(consumer) # Add to list for graceful shutdown
            logger.info(f"Kafka consumer for topic '{topic}' started successfully.")

            # Start consuming messages
            async for msg in consumer:
                logger.debug(f"Received message: topic={msg.topic}, partition={msg.partition}, offset={msg.offset}")
                try:
                    await handler(msg.value)
                except Exception as e:
                    logger.error(f"Error processing message from topic {topic}: {e}", exc_info=True)
                    # Add error handling logic here (e.g., dead-letter queue)

        except KafkaConnectionError as e:
            logger.error(f"Connection error for consumer topic '{topic}': {e}. Retrying in {retry_delay} seconds...")
            if consumer:
                await consumer.stop()
                consumers.remove(consumer)
            consumer = None
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Unexpected error in consumer for topic '{topic}': {e}. Retrying in {retry_delay} seconds...", exc_info=True)
            if consumer:
                await consumer.stop()
                consumers.remove(consumer)
            consumer = None
            await asyncio.sleep(retry_delay)
        finally:
            # Ensure consumer is stopped if loop exits unexpectedly (though it shouldn't)
            if consumer and consumer in consumers:
                try:
                    await consumer.stop()
                    consumers.remove(consumer)
                except Exception as e:
                    logger.error(f"Error stopping consumer for topic {topic} in finally block: {e}")


async def disconnect_kafka_consumers():
    logger.info(f"Disconnecting {len(consumers)} Kafka consumer(s)...")
    # Stop consuming tasks first
    for task in consumer_tasks:
        if not task.done():
            task.cancel()
    # Wait for tasks to finish cancellation
    if consumer_tasks:
        await asyncio.gather(*consumer_tasks, return_exceptions=True)

    # Stop consumer instances
    stopped_count = 0
    for consumer in list(consumers): # Iterate over a copy
        try:
            await consumer.stop()
            consumers.remove(consumer)
            stopped_count += 1
        except Exception as e:
            logger.error(f"Error stopping consumer {consumer}: {e}")
    logger.info(f"Successfully disconnected {stopped_count} Kafka consumer(s).")
    consumer_tasks.clear()

def create_consumer_task(topic: str, group_id: str, handler: Callable) -> asyncio.Task:
    """Creates an asyncio task for running a consumer."""
    task = asyncio.create_task(start_kafka_consumer(topic, group_id, handler))
    consumer_tasks.append(task)
    return task