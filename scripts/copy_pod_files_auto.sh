#!/bin/bash

# Non-interactive version of copy_pod_files.sh
# Usage: ./copy_pod_files_auto.sh <pod_name> [force]
# If 'force' is provided as second argument, it will overwrite existing directories

set -e

# Function to display usage
usage() {
    echo "Usage: $0 <pod_name> [force]"
    echo "Example: $0 oats-backend-api-646df75585-wfrsm"
    echo "Example: $0 oats-backend-api-646df75585-wfrsm force"
    echo ""
    echo "This script will automatically copy all files from pod:/app to ~/tmp_<pod_name>"
    echo "Use 'force' as second argument to overwrite existing directories"
    exit 1
}

# Check if pod name is provided
if [ $# -eq 0 ]; then
    echo "Error: Pod name is required"
    usage
fi

POD_NAME="$1"
FORCE="$2"
LOCAL_DIR="$HOME/tmp_${POD_NAME}"

echo "🔍 Checking if pod '$POD_NAME' exists..."

# Check if pod exists
if ! kubectl get pod "$POD_NAME" >/dev/null 2>&1; then
    echo "❌ Error: Pod '$POD_NAME' not found or not accessible"
    echo "Available pods:"
    kubectl get pods --no-headers | awk '{print "  - " $1}'
    exit 1
fi

echo "✅ Pod '$POD_NAME' found"

# Check if pod is running
POD_STATUS=$(kubectl get pod "$POD_NAME" -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo "⚠️  Warning: Pod is in '$POD_STATUS' state (not Running)"
    echo "Proceeding anyway..."
fi

# Handle existing directory
if [ -d "$LOCAL_DIR" ]; then
    if [ "$FORCE" = "force" ]; then
        echo "🗑️  Removing existing directory (force mode)..."
        rm -rf "$LOCAL_DIR"
    else
        echo "❌ Error: Directory $LOCAL_DIR already exists"
        echo "Use 'force' as second argument to overwrite: $0 $POD_NAME force"
        exit 1
    fi
fi

echo "📁 Creating local directory: $LOCAL_DIR"
mkdir -p "$LOCAL_DIR"

echo "📦 Copying files from pod:/app to $LOCAL_DIR..."

# Copy files from pod
if kubectl cp "$POD_NAME:/app" "$LOCAL_DIR/"; then
    echo "✅ Files copied successfully!"
    
    # Show summary
    echo ""
    echo "📊 Copy Summary:"
    echo "  Source: $POD_NAME:/app"
    echo "  Destination: $LOCAL_DIR"
    echo "  Local files: $(find "$LOCAL_DIR" -type f | wc -l)"
    echo "  Local directories: $(find "$LOCAL_DIR" -type d | wc -l)"
    
    echo ""
    echo "🎉 Done! You can now access the files at: $LOCAL_DIR"
    
else
    echo "❌ Error: Failed to copy files from pod"
    echo "Cleaning up local directory..."
    rm -rf "$LOCAL_DIR"
    exit 1
fi
