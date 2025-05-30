# Use the official Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file
# Assumes that hmrc-service/requirements.txt exists
COPY ./hmrc-service/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /app/requirements.txt

# Copy the application source code
# Assumes that the hmrc-service code is in the app folder inside hmrc-service
COPY ./hmrc-service/app /app/app

# Copy the shared folder
COPY ./shared /app/shared

# Set PYTHONPATH so that Python can find the shared module
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]
