# --- Stage 1: Build the React Application ---
    FROM node:18-alpine AS builder

    # Set the working directory
    WORKDIR /app
    
    # Copy package.json and package-lock.json to leverage Docker cache
    COPY ./services/ui/package*.json ./
    
    # Install dependencies
    RUN npm install
    
    # Copy the rest of the UI source code
    COPY ./services/ui/ ./
    
    # Build the production-ready static files
    RUN npm run build
    
    
    # --- Stage 2: Serve the Application with Nginx ---
    FROM nginx:1.25-alpine
    
    # Copy the built static files from the 'builder' stage
    COPY --from=builder /app/build /usr/share/nginx/html
    
    # Copy our custom Nginx configuration
    # We will create this file in the next step.
    COPY ./services/ui/nginx.conf /etc/nginx/conf.d/default.conf
    
    # Expose port 80 for the web server
    EXPOSE 80
    
    # Start Nginx
    CMD ["nginx", "-g", "daemon off;"]