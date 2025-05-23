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

# Custom exception for Kafka send errors
class KafkaMessageSendError(Exception):
    pass

def get_kafka_producer() -> AIOKafkaProducer:
    if producer is None:
        # Эта ошибка будет поймана, если продюсер не был инициализирован через lifespan
        # или если соединение было потеряно и producer был установлен в None.
        raise RuntimeError("Kafka producer is not initialized or connection lost.")
    return producer

async def connect_kafka_producer():
    global producer
    # Предотвращаем множественные одновременные попытки подключения, если producer уже не None, но еще не стартовал
    if producer is not None and producer._sender._sender_task is None: # Проверка, что продюсер в процессе старта/остановки
        logger.info("Kafka producer connection/disconnection already in progress. Waiting...")
        # Можно добавить более сложную логику с asyncio.Lock, если это станет проблемой
        return producer # Возвращаем текущий (возможно, неактивный) продюсер

    if producer is None: # Только если продюсер действительно None, начинаем подключение
        logger.info(f"Attempting to connect Kafka producer to {settings.KAFKA_BROKER_URL}...")
        retry_delay = 5
        # Цикл while здесь не нужен, если эта функция вызывается в цикле из lifespan
        # Оставляем для случая, если вызывается напрямую и нужна одна попытка с внутренним retry
        # Однако, основная логика retry должна быть в вызывающем коде (например, lifespan)
        # Для упрощения оставим внутренний цикл на несколько попыток, если он тут был
        # В оригинальном коде был while producer is None:
        # Если эта функция будет вызываться из lifespan в цикле, то внутренний while True не нужен.
        # Исходя из того, что функция должна просто попытаться подключить ГЛОБАЛЬНЫЙ producer:
        try:
            temp_producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                client_id=settings.KAFKA_CLIENT_ID,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                request_timeout_ms=10000,  # Таймаут на запрос к Kafka
                retry_backoff_ms=1000      # Задержка перед повторной попыткой
            )
            await temp_producer.start()
            producer = temp_producer # Устанавливаем глобальный продюсер только после успешного старта
            logger.info("Kafka producer connected successfully.")
            return producer
        except KafkaConnectionError as e:
            logger.error(f"Failed to connect Kafka producer: {e}. Will retry via background task if configured.")
            # Не устанавливаем producer = None здесь, т.к. он и так был None
            # Очистка temp_producer не нужна, он локальный
            raise # Перевыбрасываем ошибку, чтобы lifespan знал о неудаче
        except Exception as e:
            logger.error(f"An unexpected error occurred during Kafka producer connection: {e}")
            raise


async def disconnect_kafka_producer():
    global producer
    if producer:
        logger.info("Disconnecting Kafka producer...")
        try:
            await producer.stop()
            logger.info("Kafka producer disconnected successfully.")
        except Exception as e:
            logger.error(f"Error disconnecting Kafka producer: {e}")
        finally:
            producer = None # Гарантированно сбрасываем продюсер

async def send_kafka_message(topic: str, message: Dict[str, Any]):
    global producer # Нужен для установки в None в случае ошибки
    current_producer: Optional[AIOKafkaProducer] = None
    try:
        # Получаем продюсер. Если он None, get_kafka_producer выбросит RuntimeError.
        current_producer = get_kafka_producer()
    except RuntimeError as e:
        logger.error(f"Cannot send message to {topic}: {e}")
        # Продюсер не инициализирован или соединение потеряно.
        # Фоновый процесс (в lifespan) должен позаботиться о переподключении.
        raise KafkaMessageSendError(f"Producer unavailable: {e}") from e

    try:
        logger.debug(f"Sending message to Kafka topic {topic} using producer {id(current_producer)}: {message}")
        await current_producer.send_and_wait(topic, value=message)
        logger.debug(f"Message successfully sent to topic {topic}")
    except KafkaConnectionError as e:
        logger.error(f"Connection error sending message to topic {topic}: {e}. Marking producer for reconnection.")
        if current_producer: # Если продюсер был, но соединение разорвалось
            try:
                await current_producer.stop() # Попытка корректно остановить "плохой" экземпляр
            except Exception as stop_err:
                logger.error(f"Error stopping problematic producer: {stop_err}")
            finally:
                if producer is current_producer: # Убедимся, что мы сбрасываем тот же самый инстанс
                    producer = None # Сигнал для lifespan, чтобы переподключиться
        else: # Этот блок не должен достигаться, если get_kafka_producer отработал
            producer = None

        raise KafkaMessageSendError(f"Failed to send message to {topic} due to connection error: {e}") from e
    except Exception as e:
        logger.error(f"Failed to send message to topic {topic}: {e}", exc_info=True)
        # Для других ошибок также можно рассмотреть сброс продюсера, если они указывают на его неисправность
        raise KafkaMessageSendError(f"Failed to send message to {topic}: {e}") from e

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