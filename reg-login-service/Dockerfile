# Используем официальный образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
COPY ./reg-login-service/requirements.txt /app/requirements.txt

# Устанавливаем зависимости
# Используем --no-cache-dir для уменьшения размера образа
# Используем --default-timeout для предотвращения тайм-аутов при скачивании
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /app/requirements.txt

RUN pip install --no-cache-dir psycopg2-binary

# Копируем исходный код приложения в рабочую директорию
COPY ./reg-login-service/app /app/app

COPY ./alembic.ini /app/alembic.ini
COPY ./alembic /app/alembic

# Копируем общую папку shared
COPY ./shared /app/shared

COPY ./reg-login-service/run.sh /app/run.sh

# Устанавливаем PYTHONPATH, чтобы Python мог найти модуль shared
ENV PYTHONPATH "${PYTHONPATH}:/app"


# Указываем команду для запуска приложения
# Замените app.main:app на правильный путь к вашему FastAPI приложению, если он отличается
# Используем 0.0.0.0, чтобы приложение было доступно извне контейнера
# Порт 8000 по умолчанию для Uvicorn, можно изменить через --port
CMD ["/app/run.sh"]
# Используйте --reload только для разработки. Для продакшена уберите.
# Для обработки сигналов (lifespan) uvicorn подходит.