import os

# Kafka Settings
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
NHS_REQUEST_TOPIC = os.getenv("NHS_REQUEST_TOPIC", "nhs_requests")
NHS_RESPONSE_TOPIC = os.getenv("NHS_RESPONSE_TOPIC", "nhs_responses")

# Mock Service Settings
# Here you can add other settings specific to the NHS mock service,
# for example, response time, error probability, etc.
MOCK_NHS_SIMULATE_DELAY_SECONDS = int(os.getenv("MOCK_NHS_SIMULATE_DELAY_SECONDS", "1"))