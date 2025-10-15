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

# Expose port 3000 for the web server
EXPOSE 3000

# Start the application using serve
CMD ["serve", "-s", "build", "-l", "3000"]
