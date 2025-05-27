# Проект Микросервисной Системы Unity

## 1. Описание проекта

Этот проект представляет собой бэкенд микросервисной системы для упрощения доступа граждан к государственным цифровым сервисам — через сценарий записи к врачу как пример реальной интеграции. 
Система включает регистрацию и аутентификацию пользователей, верификацию данных через симулированные внешние сервисы (NHS, HMRC) и асинхронное взаимодействие компонентов через Kafka.

## 2. Архитектура

Система построена на микросервисной архитектуре и включает следующие компоненты:

*   **`api-gateway`**:
    *   Единая точка входа для всех клиентских запросов.
    *   Маршрутизирует запросы к соответствующим нижестоящим микросервисам.
    *   Может выполнять первичную валидацию, аутентификацию (например, проверку JWT).
*   **`reg-login-service`**:
    *   Отвечает за регистрацию новых пользователей.
    *   Аутентифицирует существующих пользователей (логин) и выдает JWT-токены.
    *   Управляет профилями пользователей.
    * Каждый пользователь создаёт единый цифровой профиль. Его доступ к другим госдепартаментам расширяется по мере прохождения верификации (например, NHS, налоговая служба).
    *   Взаимодействует с Kafka для запуска процесса верификации пользователя.
    * Сервис является центральной точкой управления регистрацией, авторизацией и профилем пользователя. Используется концепция централизованной IAM-системы с расширяемой архитектурой для других госдепартаментов.
*   **`nhs-service`** (симуляция):
    *   Эмулирует поведение реальных ведомств (NHS и HMRC), чтобы имитировать процесс верификации и жизненные события без подключения к внешним системам
    *   Получает запросы на верификацию из Kafka (от `reg-login-service`).
    *   Отправляет результаты верификации обратно в Kafka.
    *   Может предоставлять API для управления записями к врачу (симуляция).
*   **`hmrc-service`** (симуляция):
    *   Симулирует обработку уведомлений о смерти пользователей от HMRC.
    *   Получает события из Kafka.
    *   Может инициировать соответствующие действия в системе (например, обновление статуса пользователя).

**Технологический стек:**

*   **FastAPI**: Для создания REST API во всех Python-сервисах.
*   **Kafka**: Kafka выступает в роли асинхронной шины событий, обеспечивающей отказоустойчивое и масштабируемое взаимодействие между микросервисами
*   **PostgreSQL**: Основная база данных (используется преимущественно `reg-login-service`).
*   **Docker & Docker Compose**: Для контейнеризации, сборки и оркестрации сервисов.
*   **Pydantic**: Для валидации данных и управления настройками (через `pydantic-settings`).
*   **Uvicorn**: ASGI-сервер для запуска FastAPI приложений.
*   **SQLAlchemy**: Для взаимодействия с PostgreSQL (с асинхронным драйвером `asyncpg`).

## 3. Запуск проекта

### Предварительные требования

*   Docker (версия 20.x или выше)
*   Docker Compose (версия v2.x или выше)

### Настройка окружения

Перед первым запуском необходимо создать файлы `.env` для конфигурации каждого сервиса. Эти файлы должны находиться в корневой директории каждого соответствующего сервиса (например, `reg-login-service/.env`) и в корне проекта для PostgreSQL (`postgres.env`).

**1. Создайте `postgres.env` в корне проекта:**
```env
# postgres.env
POSTGRES_USER=ananaz      # Замените на ваше имя пользователя БД
POSTGRES_PASSWORD=ananaz # Замените на ваш пароль БД
POSTGRES_DB=microservice_db  # Замените на имя основной БД
```

**2. Создайте `.env` для `reg-login-service` (`./reg-login-service/.env`):**
```env
# ./reg-login-service/.env
DB_USER=ananaz                # Должен совпадать с postgres.env
DB_PASSWORD=ananaz       # Должен совпадать с postgres.env
DB_HOST=postgres_db                 # Имя сервиса PostgreSQL в Docker
DB_PORT=5432
DB_NAME=microservice_db           # Имя БД для этого сервиса

KAFKA_BOOTSTRAP_SERVERS=kafka:29092 # Адрес Kafka в Docker
KAFKA_CLIENT_ID=reg-login-service
IDENTITY_VERIFICATION_REQUEST_TOPIC=identity.verification.request
IDENTITY_VERIFICATION_RESULT_TOPIC=identity.verification.result
HMRC_DEATH_NOTIFICATION_TOPIC=hmrc.death.notification
KAFKA_VERIFICATION_GROUP_ID=reg-login-verification-group
KAFKA_DEATH_EVENT_GROUP_ID=reg-login-death-event-group

SECRET_KEY=your_very_strong_secret_key_for_jwt # ЗАМЕНИТЕ ЭТО!
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
BACKEND_CORS_ORIGINS="*" # Для разработки
```

**3. Создайте `.env` для `nhs-service` (`./nhs-service/.env`):**
```env
# ./nhs-service/.env
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_CLIENT_ID=nhs-service
IDENTITY_VERIFICATION_REQUEST_TOPIC=identity.verification.request
IDENTITY_VERIFICATION_RESULT_TOPIC=identity.verification.result
KAFKA_NHS_VERIFICATION_GROUP_ID=nhs-verification-group
KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST=nhs.appointment.request

SECRET_KEY=your_very_strong_secret_key_for_jwt # Должен совпадать с reg-login-service!
ALGORITHM=HS256
BACKEND_CORS_ORIGINS_NHS="*"
```

**4. Создайте `.env` для `hmrc-service` (`./hmrc-service/.env`):**
```env
# ./hmrc-service/.env
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_CLIENT_ID=hmrc-service
HMRC_DEATH_NOTIFICATION_TOPIC=hmrc.death.notification
KAFKA_HMRC_DEATH_EVENT_GROUP_ID=hmrc-death-event-group

SECRET_KEY=your_very_strong_secret_key_for_jwt # Должен совпадать с reg-login-service!
ALGORITHM=HS256
BACKEND_CORS_ORIGINS_HMRC="*"
SIMULATE_DEATH_EVENT=True
SIMULATE_DEATH_DELAY_SECONDS=30
```

**5. Создайте `.env` для `api-gateway` (`./api-gateway/.env`):**
```env
# ./api-gateway/.env
REG_LOGIN_SERVICE_URL=http://reg-login-service:80
NHS_SERVICE_URL=http://nhs-service:80
HMRC_SERVICE_URL=http://hmrc-service:80

SECRET_KEY=your_very_strong_secret_key_for_jwt # Должен совпадать с reg-login-service!
ALGORITHM=HS256
```

**Примечание:** Убедитесь, что `SECRET_KEY` является одинаковым для всех сервисов, которые работают с JWT токенами.

### Запуск сервисов

После создания `.env` файлов, запустите все сервисы с помощью Docker Compose:

```bash
docker-compose up --build -d
```

*   `--build`: пересобирает образы, если были изменения в Dockerfile или коде.
*   `-d`: запускает контейнеры в фоновом режиме.

Чтобы остановить сервисы:
```bash
docker-compose down
```

### Доступные порты (на хост-машине):
*   **API Gateway**: `http://localhost:8000`
*   **Reg-Login Service**: `http://localhost:8001` (для прямого доступа, если необходимо)
*   **NHS Service**: `http://localhost:8002` (для прямого доступа, если необходимо)
*   **HMRC Service**: `http://localhost:8003` (для прямого доступа, если необходимо)
*   **PostgreSQL**: `localhost:5432` (порт по умолчанию, если вы не меняли его в `docker-compose.yml` для `postgres_db`)
*   **Kafka Broker (для внешнего подключения, например, из Kafka UI на хосте)**: `localhost:9092`
*   **Kafka UI**: `http://localhost:8088`
*   **Zookeeper**: `localhost:2181`

## 4. Основные эндпоинты

Все запросы к API должны проходить через **API Gateway** (`http://localhost:8000`).
Ниже приведены примеры эндпоинтов, как они доступны через шлюз.

### Reg-Login Service (через API Gateway)

Предполагаемый префикс на шлюзе: `/api/v1/auth` (нужно уточнить по конфигурации API Gateway).

*   **`POST /api/v1/auth/register`** - Регистрация нового пользователя.
    *   **Тело запроса**: JSON с `email`, `password`, `identifierType` (опционально), `identifierValue` (опционально), `phoneNumber` (опционально).
    *   **Успешный ответ (201 Created)**: Данные пользователя (см. `UserResponse` в схемах).
    *   **Ошибки**: 400 (email/идентификатор существует), 422 (ошибка валидации), 500.

*   **`POST /api/v1/auth/login`** - Аутентификация пользователя.
    *   **Тело запроса**: JSON с `email`, `password`.
    *   **Успешный ответ (200 OK)**: JWT токен (см. `Token` в схемах).
    *   **Ошибки**: 401 (неверные креды), 403 (аккаунт заблокирован/не верифицирован).

*   **`GET /api/v1/auth/profile`** - Получение профиля текущего аутентифицированного пользователя.
    *   **Заголовки**: `Authorization: Bearer <your_jwt_token>`.
    *   **Успешный ответ (200 OK)**: Данные пользователя (см. `UserResponse` в схемах).
    *   **Ошибки**: 401 (не аутентифицирован).

### API Gateway

*   **`GET /`** (или другой настроенный корневой путь) - Может возвращать приветственное сообщение или информацию о шлюзе.
*   Эндпоинты, проксирующие запросы к `nhs-service` и `hmrc-service` (их конкретные пути зависят от конфигурации шлюза).

## 5. Kafka-топики

*   **`identity.verification.request`**
    *   **Producer**: `reg-login-service` (после успешной регистрации пользователя).
    *   **Consumer**: `nhs-service` (для симуляции проверки идентификатора).
*   **`identity.verification.result`**
    *   **Producer**: `nhs-service` (после обработки запроса на верификацию).
    *   **Consumer**: `reg-login-service` (для обновления статуса пользователя).
*   **`hmrc.death.notification`**
    *   **Producer**: `hmrc-service` (симуляция получения события о смерти).
    *   **Consumer**: `reg-login-service` (для обновления статуса пользователя, если он умер).
*   **`nhs.appointment.request`** (если используется `nhs-service` для записей)
    *   **Producer**: `nhs-service` (или `api-gateway` от имени клиента).
    *   **Consumer**: (Пока не ясно, какой сервис обрабатывает это в рамках симуляции).

## 6. Переменные окружения (ключевые)

Как указано в разделе "Настройка окружения", большинство настроек задается через `.env` файлы для каждого сервиса. Основные переменные:

*   **Для подключения к БД (например, в `reg-login-service/.env`):**
    *   `DB_USER`
    *   `DB_PASSWORD`
    *   `DB_HOST` (обычно имя сервиса Docker, например, `postgres_db`)
    *   `DB_PORT`
    *   `DB_NAME`
*   **Для подключения к Kafka (во всех сервисах, использующих Kafka):**
    *   `KAFKA_BOOTSTRAP_SERVERS` (например, `kafka:29092`)
    *   `KAFKA_CLIENT_ID` (уникальный для каждого сервиса)
*   **Для JWT (в `reg-login-service` и сервисах, валидирующих токен):**
    *   `SECRET_KEY`
    *   `ALGORITHM`
    *   `ACCESS_TOKEN_EXPIRE_MINUTES`
*   **Для API Gateway:**
    *   URL нижестоящих сервисов (например, `REG_LOGIN_SERVICE_URL`).

## 7. Примеры JSON-запросов/ответов

Примеры ответов для эндпоинтов `reg-login-service` находятся в директории `/api_examples/reg-login-service/` вашего проекта. Они включают:

*   `register_user_success.json`
*   `register_user_email_exists.json`
*   `register_user_identifier_exists.json`
*   `register_user_validation_error.json`
*   `register_user_server_error.json`
*   `login_success.json`
*   `login_invalid_credentials.json`
*   `login_account_blocked.json`
*   `login_account_not_verified.json`
*   `profile_get_success.json`
*   `profile_get_unauthorized.json`

**Пример запроса на регистрацию (`POST /api/v1/auth/register`):**
```json
{
  "email": "testuser@example.com",
  "password": "password123",
  "identifierType": "NIN",
  "identifierValue": "CD789012E",
  "phoneNumber": "+447000000000"
}
```

**Пример запроса на логин (`POST /api/v1/auth/login`):**
```json
{
  "email": "testuser@example.com",
  "password": "password123"
}
```

## 8. Тестирование

*   **REST API**: Можно использовать инструменты вроде [Postman](https://www.postman.com/) или `curl` для отправки запросов к API Gateway (`http://localhost:8000`). Не забывайте добавлять `Authorization: Bearer <token>` заголовок для защищенных эндпоинтов.
*   **Kafka**: Для мониторинга сообщений в топиках Kafka можно использовать Kafka UI, доступный по адресу `http://localhost:8088`.
*   **Логи**: Логи всех сервисов доступны через Docker Compose:
    ```bash
    docker-compose logs -f <имя_сервиса>
    # Например: docker-compose logs -f reg-login-service
    ```

---

Этот README.md предоставляет базовый обзор проекта. По мере развития проекта его следует дополнять и актуализировать. 