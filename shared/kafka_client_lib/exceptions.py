class KafkaClientError(Exception):
    """Base exception for Kafka client errors."""
    pass

class KafkaConnectionError(KafkaClientError):
    """Raised when connection to Kafka fails."""
    pass

class KafkaMessageSendError(KafkaClientError):
    """Raised when sending a message to Kafka fails."""
    pass

class KafkaConsumerError(KafkaClientError):
    """Raised for errors within a Kafka consumer."""
    pass 