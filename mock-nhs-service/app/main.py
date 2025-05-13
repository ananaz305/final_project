import asyncio
import logging
from fastapi import FastAPI
from .kafka.consumer import consume_nhs_requests
from .core.config import KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC
from .kafka.producer import stop_kafka_producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock NHS Service")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Mock NHS Service...")
    asyncio.create_task(consume_nhs_requests(KAFKA_BOOTSTRAP_SERVERS, NHS_REQUEST_TOPIC))
    logger.info("Kafka consumer for NHS requests started.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Mock NHS Service...")
    await stop_kafka_producer()
    # Здесь можно добавить логику для корректной остановки consumer'а, если это необходимо

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    # Эта часть для локального запуска, в Docker обычно используется другой способ
    uvicorn.run(app, host="0.0.0.0", port=8002) 