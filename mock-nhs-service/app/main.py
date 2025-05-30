import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .kafka.consumer import consume_nhs_requests
from .core.config import KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC
from .kafka.producer import stop_kafka_producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

consumer_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager to handle the FastAPI application's lifecycle.
    Executes tasks on application startup and shutdown.
    """
    global consumer_task
    logger.info("Starting Mock NHS Service...")
    consumer_task = asyncio.create_task(consume_nhs_requests(KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC))
    logger.info("Kafka consumer for NHS requests started as a background task.")

    yield

    logger.info("Shutting down Mock NHS Service...")
    if consumer_task:
        logger.info("Cancelling Kafka consumer task...")
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            logger.info("Kafka consumer task successfully cancelled.")
        except Exception as e:
            logger.error(f"Error during Kafka consumer task cancellation: {e}")

    await stop_kafka_producer()
    logger.info("Mock NHS Service shutdown complete.")

app = FastAPI(title="Mock NHS Service", lifespan=lifespan)

@app.get("/health", tags=["Health"])
async def health_check():
    """Checks the service's health status."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    # This block is for local development only; in Docker, another method is usually used.
    uvicorn.run(app, host="0.0.0.0", port=8002)
