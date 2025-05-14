import argparse
import json
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable, KafkaTimeoutError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

KAFKA_BROKER_URL = os.environ.get("KAFKA_BROKER_URL", "localhost:9092")
TARGET_TOPIC = os.environ.get("TARGET_TOPIC", 'user-events')
DEATH_REGISTRATION_TOPIC = os.environ.get("DEATH_REGISTRATION_TOPIC", "death-registrations")

def create_kafka_producer(broker_url: str):
    """Создает и возвращает экземпляр KafkaProducer."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=broker_url,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            retries=5,
            linger_ms=10,
            request_timeout_ms=30000
        )
        logger.info(f"KafkaProducer_created_successfully_for_broker: {broker_url}")
        return producer
    except NoBrokersAvailable:
        logger.error(f"No_brokers_available_at_{broker_url}. Please_check_Kafka_is_running_and_accessible.")
        return None
    except Exception as kafka_exc:
        logger.error(f"Failed_to_create_Kafka_producer: {kafka_exc}")
        return None

def send_death_event_new(producer: KafkaProducer, topic: str, event_data: dict):
    """Отправляет произвольное событие о смерти в указанный топик Kafka."""
    try:
        future = producer.send(topic, value=event_data)
        record_metadata = future.get(timeout=10)
        logger.info(
            f"Death_event_sent_successfully_to_topic='{record_metadata.topic}' "
            f"partition='{record_metadata.partition}' offset='{record_metadata.offset}'"
        )
        return True
    except KafkaTimeoutError:
        logger.error(f"Timeout_while_sending_death_event_to_topic_{topic}. The_message_may_not_have_been_sent.")
        return False
    except Exception as send_exc:
        logger.error(f"Failed_to_send_death_event: {send_exc}")
        return False

def generate_death_event_data():
    """Генерирует пример данных для события о смерти для HMRC."""
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": "DeathRegistrationReceived",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "MockHMRCService",
        "version": "1.0",
        "data": {
            "nino": f"AB{str(uuid.uuid4().int)[:7]}C",
            "forenames": "John",
            "surname": "Doe",
            "dateOfBirth": (datetime.utcnow() - timedelta(days=365*70)).strftime("%Y-%m-%d"),
            "dateOfDeath": (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "placeOfDeath": "Mock General Hospital, Anytown",
            "registrationDistrict": "AnyDistrict",
            "causeOfDeath": "Natural Causes",
        },
        "correlationId": str(uuid.uuid4())
    }

if __name__ == "__main__":
    logger.info("Attempting_to_connect_to_Kafka...")
    kafka_producer = create_kafka_producer(KAFKA_BROKER_URL)

    if kafka_producer:
        death_event_payload = generate_death_event_data()
        logger.info(f"Generated_HMRC_death_event: {json.dumps(death_event_payload, indent=2)}")

        if send_death_event_new(kafka_producer, DEATH_REGISTRATION_TOPIC, death_event_payload):
            logger.info("HMRC_death_event_script_finished_successfully.")
        else:
            logger.error("HMRC_death_event_script_finished_with_errors_sending_event.")

        try:
            kafka_producer.flush(timeout=10)
            kafka_producer.close(timeout=10)
            logger.info("Kafka_producer_closed.")
        except Exception as close_exc:
            logger.error(f"Error_closing_Kafka_producer: {close_exc}")
    else:
        logger.error("Could_not_create_Kafka_producer. Exiting_script.")
