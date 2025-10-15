# --- Single Stage: Build and Serve React Application ---
FROM node:18-alpine

# Set the working directory
WORKDIR /app

# Copy package.json and package-lock.json to leverage Docker cache
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the UI source code
COPY . ./

# Build the production-ready static files
RUN npm run build

# Install serve to serve static files
RUN npm install -g serve

# Copy the runtime config generation script
COPY generate-config.sh /app/generate-config.sh
RUN chmod +x /app/generate-config.sh

# Expose port 3000 for the web server
EXPOSE 3000

# Generate runtime config and start the application
CMD ["/bin/sh", "-c", "/app/generate-config.sh && serve -s build -l 3000"]
