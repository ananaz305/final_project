import argparse
import json
import time
import logging
from datetime import datetime, timezone
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable, KafkaTimeoutError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

KAFKA_BROKER_URL = 'kafka:9092' # Используйте переменную окружения в реальном проекте
TARGET_TOPIC = 'user-events'

def create_kafka_producer(broker_url):
    """Создает и возвращает Kafka продюсера."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=broker_url,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5, # Повторные попытки при ошибках
            request_timeout_ms=30000 # Таймаут запроса
        )
        logging.info(f"KafkaProducer connected to {broker_url}")
        return producer
    except NoBrokersAvailable:
        logging.error(f"Could not connect to Kafka broker at {broker_url}. Is Kafka running?")
        return None
    except Exception as e:
        logging.error(f"Error creating Kafka producer: {e}")
        return None

def send_death_notification(producer, user_id):
    """Отправляет уведомление о смерти в Kafka."""
    message = {
        "type": "death_notification",
        "userId": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
        # Можно добавить другие поля из реального события HMRC
    }
    try:
        future = producer.send(TARGET_TOPIC, value=message)
        # Ждем подтверждения отправки
        record_metadata = future.get(timeout=10)
        logging.info(f"Sent death notification for user {user_id} to topic '{record_metadata.topic}' partition {record_metadata.partition} offset {record_metadata.offset}")
        return True
    except KafkaTimeoutError:
        logging.error(f"Timeout sending message for user {user_id} to Kafka.")
        return False
    except Exception as e:
        logging.error(f"Error sending message for user {user_id} to Kafka: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send a mock death notification event to Kafka.')
    parser.add_argument('user_id', type=str, help='The UUID of the user.')
    args = parser.parse_args()

    logging.info("Attempting to connect to Kafka...")
    kafka_producer = create_kafka_producer(KAFKA_BROKER_URL)

    if kafka_producer:
        logging.info(f"Sending death notification for user: {args.user_id}")
        success = send_death_notification(kafka_producer, args.user_id)

        # Закрываем продюсер
        try:
            kafka_producer.flush(timeout=10) # Дожидаемся отправки всех сообщений
            kafka_producer.close(timeout=10)
            logging.info("Kafka producer closed.")
        except Exception as e:
            logging.error(f"Error closing Kafka producer: {e}")

        if success:
            logging.info("Script finished successfully.")
        else:
            logging.error("Script finished with errors.")
            exit(1)
    else:
        logging.error("Could not create Kafka producer. Exiting.")
        exit(1)