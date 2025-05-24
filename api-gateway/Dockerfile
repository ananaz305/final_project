# Используем официальный образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
# Предполагается, что api-gateway/requirements.txt существует
COPY ./requirements.txt /app/requirements.txt

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /app/requirements.txt

# Копируем исходный код приложения
# Предполагается, что код api-gateway находится в папке app внутри api-gateway
COPY ./app /app/app

# Копируем общую папку shared (если api-gateway ее использует)
# Если не использует, эти строки можно удалить для этого Dockerfile
COPY ../shared /app/shared

# Устанавливаем PYTHONPATH, чтобы Python мог найти модуль shared
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Команда для запуска приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]