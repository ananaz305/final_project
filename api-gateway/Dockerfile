# Use the official Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file
# Assumes that api-gateway/requirements.txt exists
COPY ./api-gateway/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /app/requirements.txt

# Copy the application source code
# Assumes that the api-gateway code is in the app folder inside api-gateway
COPY ./api-gateway/app /app/app

# Copy the shared folder (if api-gateway uses it)
# If not used, these lines can be removed from this Dockerfile
COPY ./shared /app/shared

# Set PYTHONPATH so that Python can find the shared module
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]
