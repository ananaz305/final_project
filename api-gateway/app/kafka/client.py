import asyncio
import json
import logging
from typing import Optional, Dict, Any
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

producer: Optional[AIOKafkaProducer] = None

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
                acks=0 # Для логов можно использовать acks=0 для макс. производительности (риск потери логов)
            )
            await producer.start()
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Kafka producer connected successfully.")
            return producer
        except KafkaConnectionError as e:
            logger.warning(f"[{settings.KAFKA_CLIENT_ID}] Failed to connect Kafka producer: {e}. Logging to Kafka will be disabled. Retrying in {retry_delay} seconds...")
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

async def send_log_message(topic: str, message: Dict[str, Any]):
    """Отправляет лог в Kafka, не блокируя основной поток и не генерируя ошибок."""
    global producer
    if not producer:
        # Не логируем каждую неудачную попытку, т.к. producer пытается переподключиться
        # logger.warning(f"[{settings.KAFKA_CLIENT_ID}] Kafka producer not available. Cannot send log to topic {topic}.")
        return # Просто не отправляем лог

    try:
        # Используем send() вместо send_and_wait() для логов - не ждем подтверждения
        await producer.send(topic, value=message)
        logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Log message sent to topic {topic}")
    except KafkaConnectionError as e:
        logger.warning(f"[{settings.KAFKA_CLIENT_ID}] Connection error sending log to topic {topic}: {e}")
        # Соединение потеряно, пытаемся восстановить в фоне
        producer = None
        asyncio.create_task(connect_kafka_producer())
    except Exception as e:
        # Логируем ошибку отправки, но не прерываем работу
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Failed to send log message to topic {topic}: {e}")