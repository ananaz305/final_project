# Using the official Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file
COPY ./reg-login-service/requirements.txt /app/requirements.txt

# Install dependencies
# Use --no-cache-dir to reduce image size
# Use --default-timeout to prevent timeouts during download
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /app/requirements.txt

RUN pip install --no-cache-dir psycopg2-binary

# Copy the application source code to the working directory
COPY ./reg-login-service/app /app/app

COPY ./alembic.ini /app/alembic.ini
COPY ./alembic /app/alembic

# Copy the shared folder
COPY ./shared /app/shared

COPY ./reg-login-service/run.sh /app/run.sh

# Set PYTHONPATH so Python can find the shared module
ENV PYTHONPATH "${PYTHONPATH}:/app"

RUN ["chmod", "+x", "/app/run.sh"]

# Specify the command to run the application
# Replace app.main:app with the correct path to your FastAPI application if it's different
# Use 0.0.0.0 so the app is accessible outside the container
# Port 8000 is the default for Uvicorn, can be changed with --port
CMD ["/app/run.sh"]
# Use --reload only for development. Remove it for production.
# Uvicorn is suitable for handling signals (lifespan).
