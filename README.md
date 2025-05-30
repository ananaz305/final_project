# Unity Microservice System Project

## 1. Project Overview

This project is a backend microservice system designed to simplify citizen access to government digital services — illustrated through a doctor appointment booking scenario as a real-world integration example.
The system includes user registration and authentication, data verification via simulated external services (NHS, HMRC), and asynchronous component communication via Kafka.

## 2. Architecture

The system is based on a microservices architecture and includes the following components:

* **`api-gateway`**:

    * Serves as a single entry point for all client requests.
    * Routes requests to the appropriate downstream microservices.
    * Can perform initial validation and authentication (e.g., JWT token checks).

* **`reg-login-service`**:

    * Handles new user registration.
    * Authenticates existing users (login) and issues JWT tokens.
    * Manages user profiles.
    * Each user creates a unified digital profile. Their access to other government departments expands as verification is completed (e.g., NHS, tax authority).
    * Interacts with Kafka to initiate user verification processes.
    * Acts as the central control point for registration, authentication, and user profile management. Implements a centralized IAM (Identity and Access Management) system with an extensible architecture for other government departments.

* **`nhs-service`** (simulation):

    * Simulates the behavior of real institutions (NHS and HMRC) to mimic verification and life events without connecting to external systems.
    * Receives verification requests from Kafka (sent by `reg-login-service`).
    * Sends verification results back to Kafka.
    * Can provide an API for managing doctor appointments (simulated).

* **`hmrc-service`** (simulation):

    * Simulates processing of death notifications from HMRC.
    * Receives events via Kafka.
    * Can initiate relevant system actions (e.g., updating user status).

**Technology Stack:**

* **FastAPI**: Used for building REST APIs in all Python services.
* **Kafka**: Acts as the asynchronous event bus, enabling resilient and scalable communication between microservices.
* **PostgreSQL**: The primary database (mainly used by `reg-login-service`).
* **Docker & Docker Compose**: For containerization, building, and orchestration of services.
* **Pydantic**: Used for data validation and configuration management (via `pydantic-settings`).
* **Uvicorn**: ASGI server for running FastAPI apps.
* **SQLAlchemy**: For interacting with PostgreSQL (using the async driver `asyncpg`).

## 3. Web interface
A simple web interface has been created for a comprehensive demonstration.
The web interface was developed using node js and react using next.js for SSR(server side render)
Web interface is also launched via docker compose.


## 4. Project Setup

### Prerequisites

* Docker (version 20.x or higher)
* Docker Compose (version v2.x or higher)

### Environment Configuration

Before the first launch, you need to create `.env` files for each service. These files should be placed in the root directory of each respective service (e.g., `reg-login-service/.env`) and in the project root for PostgreSQL (`postgres.env`).

**1. Create `postgres.env` in the project root:**

```env
# postgres.env
POSTGRES_USER=ananaz
POSTGRES_PASSWORD=ananaz
POSTGRES_DB=microservice_db
```

**2. Create `.env` for `reg-login-service` (`./reg-login-service/.env`):**

```env
DB_USER=ananaz
DB_PASSWORD=ananaz
DB_HOST=postgres_db
DB_PORT=5432
DB_NAME=microservice_db

KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_CLIENT_ID=reg-login-service
IDENTITY_VERIFICATION_REQUEST_TOPIC=identity.verification.request
IDENTITY_VERIFICATION_RESULT_TOPIC=identity.verification.result
HMRC_DEATH_NOTIFICATION_TOPIC=hmrc.death.notification
KAFKA_VERIFICATION_GROUP_ID=reg-login-verification-group
KAFKA_DEATH_EVENT_GROUP_ID=reg-login-death-event-group

SECRET_KEY=your_very_strong_secret_key_for_jwt
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
BACKEND_CORS_ORIGINS="*"
```

**3. Create `.env` for `nhs-service` (`./nhs-service/.env`):**

```env
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_CLIENT_ID=nhs-service
IDENTITY_VERIFICATION_REQUEST_TOPIC=identity.verification.request
IDENTITY_VERIFICATION_RESULT_TOPIC=identity.verification.result
KAFKA_NHS_VERIFICATION_GROUP_ID=nhs-verification-group
KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST=nhs.appointment.request

SECRET_KEY=your_very_strong_secret_key_for_jwt
ALGORITHM=HS256
BACKEND_CORS_ORIGINS_NHS="*"
```

**4. Create `.env` for `hmrc-service` (`./hmrc-service/.env`):**

```env
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_CLIENT_ID=hmrc-service
HMRC_DEATH_NOTIFICATION_TOPIC=hmrc.death.notification
KAFKA_HMRC_DEATH_EVENT_GROUP_ID=hmrc-death-event-group

SECRET_KEY=your_very_strong_secret_key_for_jwt
ALGORITHM=HS256
BACKEND_CORS_ORIGINS_HMRC="*"
SIMULATE_DEATH_EVENT=True
SIMULATE_DEATH_DELAY_SECONDS=30
```

**5. Create `.env` for `api-gateway` (`./api-gateway/.env`):**

```env
REG_LOGIN_SERVICE_URL=http://reg-login-service:80
NHS_SERVICE_URL=http://nhs-service:80
HMRC_SERVICE_URL=http://hmrc-service:80

SECRET_KEY=your_very_strong_secret_key_for_jwt
ALGORITHM=HS256
```

**Note:** Ensure `SECRET_KEY` is the same across all services that work with JWT tokens.

### Starting the Services

After creating the `.env` files, run all services using Docker Compose:

```bash
docker-compose up --build -d
```

To stop the services:

```bash
docker-compose down
```

### Available Ports (on host machine):

* **API Gateway**: `http://localhost:8000`
* **Reg-Login Service**: `http://localhost:8001` (for direct access)
* **NHS Service**: `http://localhost:8002` (for direct access)
* **HMRC Service**: `http://localhost:8003` (for direct access)
* **PostgreSQL**: `localhost:5432` (default port)
* **Kafka Broker**: `localhost:9092` (for external tools like Kafka UI)
* **Kafka UI**: `http://localhost:8088`
* **Zookeeper**: `localhost:2181`

## 5. Main Endpoints

All API requests should go through the **API Gateway** (`http://localhost:8000`).
Examples of endpoints as exposed through the gateway:

### Reg-Login Service (via API Gateway)

Expected prefix: `/api/v1/auth` (check the API Gateway config to confirm).

* **`POST /api/v1/auth/register`** – Register a new user.

    * **Request body**: JSON with `email`, `password`, `identifierType` (optional), `identifierValue` (optional), `phoneNumber` (optional).
    * **Success (201 Created)**: User data (see `UserResponse`).
    * **Errors**: 400 (email/ID exists), 422 (validation error), 500.

* **`POST /api/v1/auth/login`** – Authenticate user.

    * **Request body**: JSON with `email`, `password`.
    * **Success (200 OK)**: JWT token (see `Token` schema).
    * **Errors**: 401 (invalid credentials), 403 (account blocked/not verified).

* **`GET /api/v1/auth/profile`** – Get current user profile.

    * **Headers**: `Authorization: Bearer <your_jwt_token>`.
    * **Success (200 OK)**: User data (see `UserResponse`).
    * **Errors**: 401 (unauthenticated).

### API Gateway

* **`GET /`** – May return a welcome message or gateway info.
* Endpoints that proxy to `nhs-service` and `hmrc-service` (specific paths depend on gateway configuration).

## 6. Kafka Topics

* **`identity.verification.request`**

    * **Producer**: `reg-login-service`
    * **Consumer**: `nhs-service`

* **`identity.verification.result`**

    * **Producer**: `nhs-service`
    * **Consumer**: `reg-login-service`

* **`hmrc.death.notification`**

    * **Producer**: `hmrc-service`
    * **Consumer**: `reg-login-service`

* **`nhs.appointment.request`** (if used)

    * **Producer**: `nhs-service` (or `api-gateway`)
    * **Consumer**: Not yet defined

## 7. Environment Variables (Key Ones)

As described in the "Environment Setup" section, settings are mostly configured via `.env` files. Key variables:

* **Database connection (e.g., in `reg-login-service/.env`)**

    * `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`

* **Kafka connection (used in all Kafka-related services)**

    * `KAFKA_BOOTSTRAP_SERVERS`
    * `KAFKA_CLIENT_ID`

* **JWT settings**

    * `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

* **API Gateway service URLs**

    * e.g., `REG_LOGIN_SERVICE_URL`

## 8. Example JSON Requests/Responses

Located in `/api_examples/reg-login-service/`, including:

* `register_user_success.json`
* `register_user_email_exists.json`
* `register_user_identifier_exists.json`
* `register_user_validation_error.json`
* `register_user_server_error.json`
* `login_success.json`
* `login_invalid_credentials.json`
* `login_account_blocked.json`
* `login_account_not_verified.json`
* `profile_get_success.json`
* `profile_get_unauthorized.json`

**Sample registration request (`POST /api/v1/auth/register`):**

```json
{
  "email": "testuser@example.com",
  "password": "password123",
  "identifierType": "NIN",
  "identifierValue": "CD789012E",
  "phoneNumber": "+447000000000"
}
```

**Sample login request (`POST /api/v1/auth/login`):**

```json
{
  "email": "testuser@example.com",
  "password": "password123"
}
```

## 9. Testing

* **REST API**: Use tools like [Postman](https://www.postman.com/) or `curl` to test endpoints via `http://localhost:8000`. Don’t forget the `Authorization: Bearer <token>` header for protected endpoints.
* **Kafka**: Monitor Kafka messages using the Kafka UI at `http://localhost:8088`.
* **Logs**: View logs via Docker Compose:

  ```bash
  docker-compose logs -f <service_name>
  # Example: docker-compose logs -f reg-login-service
  ```
