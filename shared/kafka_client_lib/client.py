import asyncio
import json
import logging
from typing import Optional, List, Callable, Any, Dict, Coroutine

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError as AioKafkaConnectionError # Rename to avoid clash

from app.core.config import settings # Важно: импортируем настройки!
from shared.kafka_client_lib.exceptions import KafkaMessageSendError

# Logger for the library
logger = logging.getLogger(__name__)

# Module-level state (consider a class-based approach for better encapsulation later)
_producer: Optional[AIOKafkaProducer] = None
_active_consumers: List[AIOKafkaConsumer] = []


async def get_kafka_producer() -> AIOKafkaProducer:
    """
    Returns the active Kafka producer instance.
    Raises RuntimeError if the producer is not initialized or connection was lost.
    """
    if _producer is None:
        raise RuntimeError("Kafka producer is not initialized or connection lost.")
    return _producer

async def connect_kafka_producer(
        broker_url: str,
        client_id: str,
        connection_retry_delay_seconds: int = 5,
        request_timeout_ms: int = 10000,
        retry_backoff_ms: int = 1000
):
    """
    Attempts to connect/reconnect the Kafka producer.
    This function should be called by a managing process (e.g., lifespan) that handles retries.
    It tries to connect once and raises an exception on failure.
    """
    global _producer
    if _producer is not None:
        # If a producer instance exists, ensure it's healthy or try to stop it before creating a new one.
        # For simplicity now, we assume if _producer is not None, it's either working or will be replaced.
        # More sophisticated checks (e.g., producer._sender._running) could be added.
        logger.info("Kafka producer instance already exists. Re-connecting or replacing.")
        try:
            await _producer.stop()
        except Exception as e:
            logger.warning(f"Error stopping existing producer instance before reconnecting: {e}")
        finally:
            _producer = None # Clear it to ensure a new one is created

    logger.info(f"Attempting to connect Kafka producer to {broker_url} (client: {client_id})...")
    try:
        temp_producer = AIOKafkaProducer(
            bootstrap_servers=broker_url,
            client_id=client_id,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            request_timeout_ms=request_timeout_ms,
            retry_backoff_ms=retry_backoff_ms
        )
        await temp_producer.start()
        _producer = temp_producer
        logger.info(f"Kafka producer connected successfully to {broker_url}.")
    except AioKafkaConnectionError as e:
        logger.error(f"Failed to connect Kafka producer to {broker_url}: {e}")
        _producer = None # Ensure producer is None on failure
        raise KafkaConnectionError(f"Producer connection to {broker_url} failed: {e}") from e
    except Exception as e:
        logger.error(f"An unexpected error occurred during Kafka producer connection to {broker_url}: {e}", exc_info=True)
        _producer = None
        raise KafkaConnectionError(f"Unexpected error connecting producer to {broker_url}: {e}") from e

async def disconnect_kafka_producer():
    """Disconnects the Kafka producer if it's active."""
    global _producer
    if _producer:
        logger.info("Disconnecting Kafka producer...")
        try:
            await _producer.stop()
            logger.info("Kafka producer disconnected successfully.")
        except Exception as e:
            logger.error(f"Error disconnecting Kafka producer: {e}", exc_info=True)
        finally:
            _producer = None

async def send_kafka_message(topic: str, message: Dict[str, Any]):
    """
    Sends a message to the specified Kafka topic.
    Relies on `get_kafka_producer` to obtain the producer instance.
    If the producer is not available or sending fails, it raises KafkaMessageSendError.
    """
    global _producer # Needed to set to None on critical send failure

    active_producer: AIOKafkaProducer
    try:
        active_producer = get_kafka_producer() # Raises RuntimeError if None
    except RuntimeError as e:
        logger.warning(f"Cannot send message to topic '{topic}': Producer not available. A background reconnect might be needed.")
        raise KafkaMessageSendError(f"Producer unavailable: {e}") from e

    try:
        logger.debug(f"Sending message to Kafka topic '{topic}': {message}")
        await active_producer.send_and_wait(topic, value=message)
        logger.debug(f"Message successfully sent to topic '{topic}'.")
    except AioKafkaConnectionError as e: # Specific error from aiokafka
        logger.error(f"Kafka connection error sending message to topic '{topic}': {e}. Marking producer for reconnection.")
        # Attempt to clean up the faulty producer instance
        if _producer is active_producer: # ensure we are operating on the global instance
            try:
                await _producer.stop()
            except Exception as stop_err:
                logger.error(f"Error stopping problematic producer after send failure: {stop_err}", exc_info=True)
            finally:
                _producer = None # Signal that the producer needs reconnection
        raise KafkaMessageSendError(f"Failed to send message to '{topic}' due to Kafka connection error: {e}") from e
    except Exception as e: # Other errors (e.g., serialization, unexpected)
        logger.error(f"An unexpected error occurred sending message to topic '{topic}': {e}", exc_info=True)
        # For other critical errors, also consider resetting the producer
        if _producer is active_producer:
            _producer = None
        raise KafkaMessageSendError(f"Unexpected error sending message to '{topic}': {e}") from e

async def send_kafka_message_fire_and_forget(topic: str, message: Dict[str, Any]):
    """
    Sends a message to the specified Kafka topic without waiting for confirmation (fire and forget).
    Useful for non-critical messages like logs.
    Handles errors by logging them, does not propagate KafkaMessageSendError for send issues unless producer is unavailable.
    """
    global _producer # Needed to set to None on critical send failure that might affect producer state

    active_producer: AIOKafkaProducer
    try:
        active_producer = get_kafka_producer() # Raises RuntimeError if None
    except RuntimeError as e:
        logger.warning(f"Cannot send fire-and-forget message to topic '{topic}': Producer not available. {e}")
        # No exception raised here as it's fire and forget, but producer might need reconnection by background task.
        return

    try:
        logger.debug(f"Sending fire-and-forget message to Kafka topic '{topic}': {message}")
        await active_producer.send(topic, value=message) # Use send() instead of send_and_wait()
        logger.debug(f"Fire-and-forget message enqueued to topic '{topic}'.")
    except AioKafkaConnectionError as e:
        logger.error(f"Kafka connection error sending fire-and-forget message to topic '{topic}': {e}. Marking producer for reconnection.")
        if _producer is active_producer:
            try:
                await _producer.stop()
            except Exception as stop_err:
                logger.error(f"Error stopping problematic producer after fire-and-forget send failure: {stop_err}", exc_info=True)
            finally:
                _producer = None # Signal that the producer needs reconnection
        # Do not raise KafkaMessageSendError for fire-and-forget unless it's a setup issue (handled by get_kafka_producer)
    except Exception as e:
        logger.error(f"An unexpected error occurred sending fire-and-forget message to topic '{topic}': {e}", exc_info=True)
        # For other critical errors, also consider resetting the producer
        if _producer is active_producer:
            _producer = None
        # Do not raise KafkaMessageSendError

async def start_kafka_consumer(
        topic: str,
        group_id: str,
        broker_url: str,
        client_id_prefix: str, # e.g., settings.KAFKA_CLIENT_ID
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
        consumer_retry_delay_seconds: int = 5,
        value_deserializer: Optional[Callable[[bytes], Any]] = None,
        auto_offset_reset: str = 'earliest',
        enable_auto_commit: bool = True
):
    """
    Starts a Kafka consumer for a specific topic and group_id.
    Manages connection retries internally.
    The handler is an async function that processes a single message.
    This function will run indefinitely until cancelled.
    """
    global _active_consumers

    if value_deserializer is None:
        value_deserializer = lambda v: json.loads(v.decode('utf-8'))

    consumer_instance: Optional[AIOKafkaConsumer] = None
    logger.info(f"Kafka consumer for topic '{topic}' (group: '{group_id}') starting...")

    while True:
        try:
            consumer_instance = AIOKafkaConsumer(
                topic,
                bootstrap_servers=broker_url,
                group_id=group_id,
                client_id=f"{client_id_prefix}-{group_id}-{topic}", # More specific client ID
                value_deserializer=value_deserializer,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=enable_auto_commit,
                # auto_commit_interval_ms=5000 # Default is 5000
            )
            await consumer_instance.start()
            _active_consumers.append(consumer_instance)
            logger.info(f"Kafka consumer for topic '{topic}' (group: '{group_id}') connected and running.")

            async for msg in consumer_instance:
                logger.debug(f"Received message: topic={msg.topic}, part={msg.partition}, offset={msg.offset} for group '{group_id}'")
                try:
                    await handler(msg.value)
                except Exception as e:
                    logger.error(f"Error processing message from topic '{topic}' in group '{group_id}': {e}", exc_info=True)
                    # Consider adding logic for dead-letter queues or specific error handling based on exception type.

        except AioKafkaConnectionError as e:
            logger.error(f"Kafka connection error for consumer topic '{topic}' (group: '{group_id}'): {e}. Retrying in {consumer_retry_delay_seconds}s.")
        except asyncio.CancelledError:
            logger.info(f"Kafka consumer for topic '{topic}' (group: '{group_id}') was cancelled.")
            break # Exit the while loop
        except Exception as e: # Includes other Kafka errors or unexpected issues
            logger.error(f"Unexpected error in consumer for topic '{topic}' (group: '{group_id}'): {e}. Retrying in {consumer_retry_delay_seconds}s.", exc_info=True)
        finally:
            if consumer_instance:
                try:
                    await consumer_instance.stop()
                    logger.info(f"Kafka consumer for topic '{topic}' (group: '{group_id}') stopped.")
                except Exception as e:
                    logger.error(f"Error stopping consumer '{topic}' (group: '{group_id}') in finally: {e}", exc_info=True)
                if consumer_instance in _active_consumers:
                    _active_consumers.remove(consumer_instance)
                consumer_instance = None # Reset for the next retry iteration

        if not asyncio.current_task().cancelled(): # Only sleep if not cancelled
            await asyncio.sleep(consumer_retry_delay_seconds)
        else: # If cancelled during the error handling or sleep
            logger.info(f"Kafka consumer task for topic '{topic}' (group: '{group_id}') detected cancellation during retry/cleanup.")
            break


async def disconnect_kafka_consumers():
    """
    Stops all active Kafka consumers managed by this library module.
    This is typically called during application shutdown.
    Note: This stops consumers started by `start_kafka_consumer` and added to `_active_consumers`.
    It does NOT cancel asyncio tasks that might be running these consumers;
    task cancellation should be handled by the application's lifecycle management.
    """
    global _active_consumers
    logger.info(f"Disconnecting {len(_active_consumers)} Kafka consumer(s) managed by the library...")

    # Create a copy for iteration as items might be removed
    for consumer in list(_active_consumers):
        try:
            await consumer.stop()
            logger.info(f"Successfully stopped consumer for topics: {consumer.subscription()}")
            if consumer in _active_consumers: # Check again as it might have been removed by itself
                _active_consumers.remove(consumer)
        except Exception as e:
            logger.error(f"Error stopping consumer instance {consumer}: {e}", exc_info=True)
            # Even if stopping failed, try to remove it from the list
            if consumer in _active_consumers:
                _active_consumers.remove(consumer)

    logger.info(f"All managed Kafka consumers have been requested to stop. Remaining in list: {len(_active_consumers)}")
    # _active_consumers should ideally be empty here if all stops were successful and clean. 