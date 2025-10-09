# Use a slim Python base image
FROM python:3.9-slim

WORKDIR /app

# Install dependencies, including the Kubernetes client
COPY ./services/backend-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source code
COPY ./services/backend-api/app/ .

# Expose the port the API will run on
EXPOSE 8000

# Start the Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]