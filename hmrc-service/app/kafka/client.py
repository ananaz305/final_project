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