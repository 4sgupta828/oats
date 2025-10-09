# Use a slim Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY ./services/agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the agent's source code into the container
COPY ./services/agent/agent/ .

# Define the command to run when the container starts
CMD ["python", "main.py"]