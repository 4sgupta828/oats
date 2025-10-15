#!/bin/sh
# Generate runtime configuration for React app
# This script runs at container startup to inject environment-specific config

# Default to localhost if not set
BACKEND_URL=${REACT_APP_BACKEND_URL:-http://localhost:8000}

# Create runtime config file that will be loaded by the app
cat > /app/build/config.js <<EOF
window.RUNTIME_CONFIG = {
  BACKEND_URL: '${BACKEND_URL}'
};
EOF

echo "Generated runtime config with BACKEND_URL=${BACKEND_URL}"
