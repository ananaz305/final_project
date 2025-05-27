#!/bin/sh

cd /app
alembic revision --autogenerate -m "init"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 80 --reload