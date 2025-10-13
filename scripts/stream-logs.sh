#!/bin/bash

# Script to stream logs from Kubernetes pods in real-time
# Also saves to /logs directory

set -e

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

LOG_TYPE=${1:-both}  # agent, ui, or both (default)

echo -e "${GREEN}📡 Streaming logs from AWS EKS cluster...${NC}"

# Determine logs directory - use /logs if writable, otherwise use local logs/
if [ -w /logs ] 2>/dev/null; then
    LOGS_DIR="/logs"
elif [ -d /logs ] && [ -w /logs/.. ]; then
    LOGS_DIR="/logs"
else
    # Fall back to local directory
    LOGS_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"
    mkdir -p "$LOGS_DIR"
fi

echo -e "${YELLOW}Logs will be saved to: $LOGS_DIR${NC}"

# Function to stream and save logs
stream_logs() {
    local POD_NAME=$1
    local LOG_FILE=$2
    local LABEL=$3

    echo -e "${BLUE}[$LABEL] Starting log stream...${NC}"
    kubectl logs -f "$POD_NAME" 2>&1 | while IFS= read -r line; do
        echo -e "${BLUE}[$LABEL]${NC} $line"
        echo "$line" >> "$LOG_FILE"
    done
}

# Get pod names
BACKEND_POD=$(kubectl get pods -l app=oats-backend-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
UI_POD=$(kubectl get pods -l app=oats-ui -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

case $LOG_TYPE in
    agent)
        if [ -z "$BACKEND_POD" ]; then
            echo -e "${RED}❌ No oats-backend-api pod found${NC}"
            exit 1
        fi
        rm -f "$LOGS_DIR/agent.log"
        touch "$LOGS_DIR/agent.log"
        echo -e "${GREEN}✓ Streaming agent logs (saving to $LOGS_DIR/agent.log)${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        stream_logs "$BACKEND_POD" "$LOGS_DIR/agent.log" "AGENT"
        ;;
    ui)
        if [ -z "$UI_POD" ]; then
            echo -e "${RED}❌ No oats-ui pod found${NC}"
            exit 1
        fi
        rm -f "$LOGS_DIR/ui.log"
        touch "$LOGS_DIR/ui.log"
        echo -e "${GREEN}✓ Streaming UI logs (saving to $LOGS_DIR/ui.log)${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        stream_logs "$UI_POD" "$LOGS_DIR/ui.log" "UI"
        ;;
    both)
        if [ -z "$BACKEND_POD" ] && [ -z "$UI_POD" ]; then
            echo -e "${RED}❌ No pods found${NC}"
            exit 1
        fi

        # Clear old logs
        rm -f "$LOGS_DIR/agent.log" "$LOGS_DIR/ui.log"
        touch "$LOGS_DIR/agent.log" "$LOGS_DIR/ui.log"

        echo -e "${GREEN}✓ Streaming both agent and UI logs${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""

        # Stream both in parallel
        if [ -n "$BACKEND_POD" ]; then
            stream_logs "$BACKEND_POD" "$LOGS_DIR/agent.log" "AGENT" &
        fi
        if [ -n "$UI_POD" ]; then
            stream_logs "$UI_POD" "$LOGS_DIR/ui.log" "UI" &
        fi

        # Wait for both background processes
        wait
        ;;
    *)
        echo -e "${RED}Usage: $0 [agent|ui|both]${NC}"
        exit 1
        ;;
esac
