# Копируем содержимое из nhs-service/app/kafka/client.py,
# адаптируя топики и, возможно, логику если HMRC требует других данных
# или форматов для своих событий (например, Death Notification).
# В данном примере, для простоты, структура Kafka Producer и Consumer
# может быть очень похожей на ту, что в reg-login-service или nhs-service.

# Потенциальное содержимое (пример):

# from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
# import json
# import asyncio
# from app.core.config import settings
# from app.core.logging_config import logger

# class KafkaProducerWrapper:
#     def __init__(self, bootstrap_servers: str):
#         self.bootstrap_servers = bootstrap_servers
#         self._producer = None

#     async def start(self):
#         self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
#         await self._producer.start()
#         logger.info(f"Kafka Producer connected to {self.bootstrap_servers}")

#     async def stop(self):
#         if self._producer:
#             await self._producer.stop()
#             logger.info("Kafka Producer disconnected")

#     async def send(self, topic: str, message: dict):
#         if not self._producer:
#             logger.error("Producer not started. Call start() first.")
#             # Или можно добавить автоматический старт, если это предпочтительно
#             # await self.start()
#             raise Exception("Kafka producer not initialized")
#         try:
#             value_bytes = json.dumps(message).encode('utf-8')
#             await self._producer.send_and_wait(topic, value_bytes)
#             logger.info(f"Message sent to topic {topic}: {message}")
#         except Exception as e:
#             logger.error(f"Failed to send message to topic {topic}: {e}")
#             # Здесь можно добавить логику повторных попыток или обработки ошибок

# # Синглтон для Kafka Producer (если используется)
# # kafka_producer_instance = KafkaProducerWrapper(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)

# # async def get_kafka_producer():
# #     return kafka_producer_instance

# # Пример функции для отправки уведомления о смерти (специфично для HMRC)
# # async def send_death_notification(user_id: str, notification_details: dict):
# #     message = {
# #         "user_id": user_id,
# #         "type": "DEATH_NOTIFICATION",
# #         "details": notification_details
# #     }
# #     await kafka_producer_instance.send(settings.HMRC_DEATH_NOTIFICATION_TOPIC, message)


# # Для Kafka Consumer (если HMRC-сервис что-то слушает)
# # async def consume_some_topic():
# #     consumer = AIOKafkaConsumer(
# #         settings.SOME_HMRC_TOPIC, # Пример топика
# #         bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
# #         group_id="hmrc-group", # Пример группы
# #         auto_offset_reset="earliest"
# #     )
# #     await consumer.start()
# #     logger.info(f"Kafka Consumer for {settings.SOME_HMRC_TOPIC} started.")
# #     try:
# #         async for msg in consumer:
# #             try:
# #                 message_data = json.loads(msg.value.decode('utf-8'))
# #                 logger.info(f"Received message from {msg.topic}: {message_data}")
# #                 # Здесь обработка сообщения
# #                 # Например, await handle_hmrc_message(message_data)
# #             except json.JSONDecodeError:
# #                 logger.error(f"Failed to decode JSON message from {msg.topic}: {msg.value.decode('utf-8')}")
# #             except Exception as e:
# #                 logger.error(f"Error processing message from {msg.topic}: {e}")
# #     finally:
# #         await consumer.stop()
# #         logger.info(f"Kafka Consumer for {settings.SOME_HMRC_TOPIC} stopped.")

import asyncio
import json
import logging
from typing import List, Callable, Any, Dict, Coroutine
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError, KafkaTimeoutError

from app.core.config import settings

logger = logging.getLogger(__name__)

producer: AIOKafkaProducer | None = None
consumer: AIOKafkaConsumer | None = None
consumer_task: asyncio.Task | None = None

async def connect_kafka_producer():
    """Инициализирует и подключает Kafka Producer."""
    global producer
    if producer is None or producer._sender.sender_task.done(): # Check if producer is None or its task is done
        logger.info(f"Connecting to Kafka producer at {settings.KAFKA_BROKER_URL}")
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                client_id=settings.KAFKA_CLIENT_ID_PRODUCER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                enable_idempotence=True # Гарантирует, что сообщения будут записаны ровно один раз
            )
            await producer.start()
            logger.info("Kafka producer connected successfully.")
        except KafkaConnectionError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")
            producer = None # Reset producer on failure
            # Consider re-raising or handling appropriately (e.g. retry logic)
            raise
    else:
        logger.info("Kafka producer already connected.")

async def disconnect_kafka_producer():
    """Отключает Kafka Producer."""
    global producer
    if producer:
        logger.info("Disconnecting Kafka producer...")
        await producer.stop()
        producer = None
        logger.info("Kafka producer disconnected.")

async def send_kafka_message(topic: str, message: dict, key: str | None = None):
    """Отправляет сообщение в указанный Kafka топик."""
    if producer is None:
        logger.error("Kafka producer is not initialized. Cannot send message.")
        # Можно добавить попытку переподключения или выбросить исключение
        # await connect_kafka_producer() # Попытка переподключения
        # if producer is None: # Если все еще не подключен
        raise RuntimeError("Kafka producer is not available. Please ensure it's connected.")

    logger.debug(f"Sending message to topic '{topic}': {message}")
    try:
        key_bytes = key.encode('utf-8') if key else None
        future = await producer.send_and_wait(topic, value=message, key=key_bytes)
        logger.info(f"Message sent to topic '{topic}', offset: {future.offset}, partition: {future.partition}")
    except KafkaTimeoutError:
        logger.error(f"Timeout sending message to topic '{topic}'. Message: {message}")
        # Здесь можно добавить логику повторной отправки или обработки ошибки
        raise
    except Exception as e:
        logger.error(f"Error sending message to Kafka topic '{topic}': {e}. Message: {message}")
        raise

def get_kafka_producer() -> AIOKafkaProducer:
    """Возвращает инстанс Kafka Producer. Выбрасывает RuntimeError если он не инициализирован."""
    if producer is None:
        raise RuntimeError("Kafka producer is not initialized. Call connect_kafka_producer first.")
    return producer

# --- Consumer Related Functions (hmrc-service specific) ---

async def start_kafka_consumer(
        topics: List[str],
        group_id: str,
        message_handler: Callable[[Dict[Any, Any]], Coroutine[Any, Any, None]]
):
    """
    Инициализирует и запускает Kafka Consumer для указанных топиков и группы.
    Каждое полученное сообщение обрабатывается с помощью `message_handler`.
    """
    global consumer, consumer_task
    if consumer is not None or consumer_task is not None:
        logger.warning("Kafka consumer or consumer task already running. Stopping existing one first.")
        await stop_kafka_consumer()

    logger.info(f"Initializing Kafka consumer for topics: {topics}, group_id: {group_id}")
    try:
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            client_id=settings.KAFKA_CLIENT_ID_CONSUMER,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest', # Начинать с самого раннего сообщения, если нет сохраненного offset
            enable_auto_commit=True, # Автоматический коммит offset'ов
            auto_commit_interval_ms=5000 # Интервал авто-коммита
            # metadata_max_age_ms=..., # Можно настроить для более быстрого обнаружения новых партиций/топиков
        )
        await consumer.start()
        logger.info(f"Kafka consumer started for topics: {topics}, group_id: {group_id}")

        async def consume_messages():
            try:
                async for msg in consumer: # type: ignore
                    logger.info(f"Received message on topic '{msg.topic}', partition={msg.partition}, offset={msg.offset}, key={msg.key}")
                    logger.debug(f"Message value: {msg.value}")
                    try:
                        await message_handler(msg.value) # msg.value уже десериализовано
                    except Exception as e:
                        logger.error(f"Error processing message from topic '{msg.topic}': {e}. Message: {msg.value}", exc_info=True)
                        # Решить, что делать с ошибочными сообщениями: пропустить, отправить в dead letter queue и т.д.
            except asyncio.CancelledError:
                logger.info("Consumer task cancelled. Stopping consumer...")
            except Exception as e:
                logger.error(f"Kafka consumer error: {e}", exc_info=True)
            finally:
                if consumer:
                    logger.info("Stopping consumer from within consume_messages task...")
                    await consumer.stop()
                    logger.info("Consumer stopped from within consume_messages task.")

        consumer_task = asyncio.create_task(consume_messages())
        logger.info("Kafka consumer task created and started.")

    except KafkaConnectionError as e:
        logger.error(f"Failed to connect Kafka consumer for topics {topics}: {e}")
        consumer = None
        consumer_task = None
        # Можно добавить логику переподключения или выбросить исключение
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred while starting Kafka consumer: {e}", exc_info=True)
        if consumer:
            await consumer.stop()
        consumer = None
        consumer_task = None
        raise

async def stop_kafka_consumer():
    """Останавливает Kafka Consumer и его задачу обработки сообщений."""
    global consumer, consumer_task
    logger.info("Attempting to stop Kafka consumer and task...")

    if consumer_task and not consumer_task.done():
        logger.info("Cancelling Kafka consumer task...")
        consumer_task.cancel()
        try:
            await consumer_task
            logger.info("Kafka consumer task finished after cancellation.")
        except asyncio.CancelledError:
            logger.info("Kafka consumer task was cancelled successfully.")
        except Exception as e:
            logger.error(f"Exception during consumer task shutdown: {e}", exc_info=True)
    else:
        logger.info("Kafka consumer task not found or already done.")

    if consumer:
        logger.info("Stopping Kafka consumer client...")
        try:
            await consumer.stop()
            logger.info("Kafka consumer client stopped successfully.")
        except Exception as e:
            logger.error(f"Error stopping Kafka consumer client: {e}", exc_info=True)

    consumer = None
    consumer_task = None
    logger.info("Kafka consumer and task are now None.")

def get_kafka_consumer() -> AIOKafkaConsumer | None:
    """Возвращает инстанс Kafka Consumer если он активен, иначе None."""
    return consumer