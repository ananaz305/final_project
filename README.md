# Микросервисный прототип на Python (FastAPI + Kafka + PostgreSQL)

Данный проект представляет собой прототип микросервисной архитектуры, переписанный на Python с использованием FastAPI, SQLAlchemy, aiokafka.
Он реализует базовые требования по регистрации пользователей, асинхронной верификации через Kafka и проксирование запросов через API Gateway.

## Компоненты Системы

- **API Gateway** (`api-gateway/`) - Точка входа, проксирование запросов, валидация JWT (порт 8000)
- **Сервис Регистрации/Логина** (`reg-login-service/`) - Управление пользователями, аутентификация (email+пароль), выдача JWT (порт 8002)
- **Сервис NHS (NHS)** (`nhs-service/`) - Обработка NHS-специфичных запросов и верификации (порт 8001)
- **Сервис HMRC** (`hmrc-service/`) - Обработка HMRC-специфичных запросов, уведомления о смерти (порт 8003)
- **Kafka** (`kafka/`) - Брокер сообщений для асинхронного взаимодействия.

## Требования

- Python 3.10+
- Poetry (рекомендуется) или pip
- Запущенный брокер Kafka (localhost:9092 по умолчанию)
- Запущенный сервер PostgreSQL (localhost:5432 по умолчанию) с созданной базой данных (по умолчанию `reg_login_db`) и пользователем/паролем (см. `.env.example` или конфигурацию сервисов).

## Установка

1.  Клонируйте репозиторий:
    ```bash
    git clone <repository-url>
    cd <project-directory>
    ```

2.  **Настройка окружения (рекомендуется):**
    Создайте и активируйте виртуальное окружение:
    ```bash
    python -m venv .venv
    source .venv/bin/activate # Linux/macOS
    # .\.venv\Scripts\activate # Windows
    ```

3.  **Установка зависимостей:**
    Установите все зависимости из `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Настройка переменных окружения:**
    Скопируйте `.env.example` (если он будет создан) в `.env` и измените параметры подключения к БД, Kafka, секретные ключи и т.д. при необходимости. Либо установите соответствующие переменные окружения в вашей системе.
    **Важно:** Убедитесь, что `SECRET_KEY` одинаковый для `reg-login-service` и `api-gateway` для корректной работы JWT (пока используется). Создайте базу данных PostgreSQL, указанную в `DB_NAME`.

## Запуск

Каждый сервис является независимым FastAPI приложением и запускается с помощью `uvicorn`.

**Запуск всех сервисов (в отдельных терминалах):**

```bash
# Терминал 1: API Gateway
cd api-gateway
# Порт по умолчанию 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 

# Терминал 2: Сервис Регистрации/Логина
cd reg-login-service
# Порт по умолчанию 8001
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload 

# Терминал 3: Сервис NHS
cd nhs-service
# Порт по умолчанию 8002
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload 

# Терминал 4: Сервис HMRC
cd hmrc-service
# Порт по умолчанию 8003
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload 
```

Флаг `--reload` включает автоматическую перезагрузку при изменении кода (удобно для разработки).

## Тестирование (Примеры)

*(Предполагается, что API Gateway запущен на порту 8000)*

### 1. Регистрация нового пользователя (NIN)

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test.nin@example.com",
    "identifierType": "NIN",
    "identifierValue": "AB123456C",
    "password": "password123",
    "phoneNumber": "+447123456789"
  }'
```

*(Ожидаемый ответ: 201 Created с данными пользователя)*

### 2. Регистрация нового пользователя (NHS)

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test.nhs@example.com",
    "identifierType": "NHS",
    "identifierValue": "NHS123456789",
    "password": "password123"
  }'
```

### 3. Вход в систему

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test.nin@example.com",
    "password": "password123"
  }'
```

*(Ожидаемый ответ: 200 OK с `access_token`)*
Сохраните полученный `access_token`.

### 4. Получение профиля

```bash
TOKEN="ваш_access_token"
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Попытка доступа к защищенному ресурсу NHS

```bash
curl -X GET http://localhost:8000/api/nhs/patients \
  -H "Authorization: Bearer $TOKEN" -v
```
*(Ожидаемый ответ: 200 OK, если токен валиден. Дополнительная авторизация по ролям/статусу пока не реализована полностью.)*

### 6. Наблюдение за логами Kafka

Используйте инструменты вроде `kafkacat` или UI (например, Conduktor, Offset Explorer) для просмотра сообщений в топиках:
`identity.verification.request`, `identity.verification.result`, `hmrc.death.notification`, `system.logs.activity`, `system.logs.access`.

Вы увидите запросы на верификацию, ответы от NHS/HMRC сервисов, уведомление о смерти (через 30с после старта HMRC сервиса) и логи активности/доступа от API Gateway.

## Архитектура (Python)

- **FastAPI:** Используется во всех сервисах для создания асинхронных API.
- **Uvicorn:** ASGI сервер для запуска FastAPI приложений.
- **SQLAlchemy (asyncio):** ORM для асинхронной работы с PostgreSQL в `reg-login-service`.
- **Asyncpg:** Асинхронный драйвер для PostgreSQL.
- **AIOKafka:** Асинхронный клиент Kafka для обмена сообщениями между сервисами.
- **Pydantic:** Для валидации данных и настроек.
- **Httpx:** Асинхронный HTTP клиент в API Gateway для проксирования запросов.
- **Passlib/Bcrypt:** Для хеширования паролей.
- **Python-jose:** Для работы с JWT (временная замена Keycloak).

## Следующие шаги / Улучшения

- **Интеграция с Keycloak:** Заменить текущую JWT-аутентификацию на OAuth2/OIDC с Keycloak.
- **Авторизация (RBAC/PBAC):** Реализовать проверку ролей/политик в API Gateway на основе данных из токена Keycloak.
- **Реализация Use Case "Запись к врачу":** Добавить логику в `nhs-service`.
- **Обработка ошибок Kafka:** Добавить более надежную обработку ошибок (retry, dead-letter queues).
- **Миграции БД:** Использовать Alembic для управления схемой базы данных.
- **Тестирование:** Написать unit и integration тесты.
- **Контейнеризация:** Добавить Dockerfile и docker-compose.yml для упрощения развертывания.
- **Конфигурация:** Вынести больше настроек в переменные окружения / `.env` файл.
- **Реальные API адаптеры:** Заменить заглушки для NHS/HMRC API.

## Журнал событий (Kafka)

Откройте еще один терминал и запустите скрипт для прослушивания всех топиков Kafka:
```bash
python kafka-utils/kafka_consumer_all_topics.py
```
Вы увидите запросы на верификацию, ответы от NHS/HMRC сервисов, уведомление о смерти (через 30с после старта HMRC сервиса) и логи активности/доступа от API Gateway.

### Задачи для дальнейшей разработки (Backlog)

- **Разработка UI для взаимодействия с API.**
- **Интеграция с реальными API NHS и HMRC (если возможно).**
- **Улучшение логики PBAC (Policy-Based Access Control).**
- **Реализация Use Case "Запись к врачу":** Добавить логику в `nhs-service`.
- **Расширенное логгирование и мониторинг.**
- **Написание Unit и Integration тестов.**
   
