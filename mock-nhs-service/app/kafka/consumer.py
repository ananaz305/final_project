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
        group_id="nhs_mock_service_group", # A unique group_id for consumer
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset="earliest" # Start reading from the earliest message if there is no saved offset.
    )
    await consumer.start()
    logger.info(f"Consumer started for topic: {topic}")
    try:
        async for msg in consumer:
            logger.info(f"Received message: {msg.value} from topic {msg.topic} partition {msg.partition} offset {msg.offset}")
            try:
                request_data = msg.value
                # Simulation of processing delay
                await asyncio.sleep(MOCK_NHS_SIMULATE_DELAY_SECONDS)

                # Sending data to the handler
                await handle_nhs_request(request_data)

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON message: {msg.value}")
            except Exception as e:
                logger.error(f"Error processing message: {msg.value}, error: {e}")
            # In a real application, there may also be logic for sending a message to DLQ (Dead Letter Queue)
            # or confirmation of message processing (commit offset), depending on the consumer's settings
    finally:
        logger.info("Stopping consumer...")
        await consumer.stop()
        logger.info("Consumer stopped.")

if __name__ == '__main__':
    # This is for the possibility of launching the consumer separately for testing
    async def main():
        await consume_nhs_requests(KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC)

    asyncio.run(main())