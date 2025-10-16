#!/bin/bash

# Script to copy files from a Kubernetes pod's /app directory to local ~/tmp_{podId}
# Usage: ./copy_pod_files.sh <pod_name>

set -e  # Exit on any error

# Function to display usage
usage() {
    echo "Usage: $0 <pod_name>"
    echo "Example: $0 oats-backend-api-646df75585-wfrsm"
    echo ""
    echo "This script will:"
    echo "1. Check if the pod exists"
    echo "2. Create ~/tmp_<pod_name> directory"
    echo "3. Copy all files from pod:/app to the local directory"
    exit 1
}

# Check if pod name is provided
if [ $# -eq 0 ]; then
    echo "Error: Pod name is required"
    usage
fi

POD_NAME="$1"
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
    read -p "Do you want to continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted by user"
        exit 1
    fi
fi

echo "📁 Creating local directory: $LOCAL_DIR"

# Create local directory
if [ -d "$LOCAL_DIR" ]; then
    echo "⚠️  Directory $LOCAL_DIR already exists"
    read -p "Do you want to remove it and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Removing existing directory..."
        rm -rf "$LOCAL_DIR"
    else
        echo "Aborted by user"
        exit 1
    fi
fi

mkdir -p "$LOCAL_DIR"

echo "📋 Checking files in pod:/app..."

# List files in pod:/app for confirmation
echo "Files in pod:/app:"
kubectl exec "$POD_NAME" -- ls -la /app | head -20
FILE_COUNT=$(kubectl exec "$POD_NAME" -- find /app -type f | wc -l)
echo "Total files to copy: $FILE_COUNT"

read -p "Do you want to proceed with copying? (Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Aborted by user"
    exit 1
fi

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
    echo "📁 Directory structure:"
    tree "$LOCAL_DIR" -L 2 2>/dev/null || ls -la "$LOCAL_DIR"
    
    echo ""
    echo "🎉 Done! You can now access the files at: $LOCAL_DIR"
    
else
    echo "❌ Error: Failed to copy files from pod"
    echo "Cleaning up local directory..."
    rm -rf "$LOCAL_DIR"
    exit 1
fi
