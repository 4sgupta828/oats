#!/bin/bash

# Script to download logs from Kubernetes pods running in AWS EKS
# Saves logs to logs directory as agent.log and ui.log

set -e

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔍 Fetching logs from AWS EKS cluster...${NC}"

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

# Get backend pod name (agent)
echo -e "${GREEN}📦 Finding oats-backend-api pod...${NC}"
BACKEND_POD=$(kubectl get pods -l app=oats-backend-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$BACKEND_POD" ]; then
    echo -e "${RED}❌ No oats-backend-api pod found${NC}"
else
    echo -e "${GREEN}✓ Found backend pod: $BACKEND_POD${NC}"
    echo -e "${YELLOW}Downloading agent logs...${NC}"
    kubectl logs "$BACKEND_POD" --tail=10000 > "$LOGS_DIR/agent.log" 2>&1
    LINE_COUNT=$(wc -l < "$LOGS_DIR/agent.log" | tr -d ' ')
    FILE_SIZE=$(du -h "$LOGS_DIR/agent.log" | cut -f1)
    echo -e "${GREEN}✓ Agent logs saved to $LOGS_DIR/agent.log ($LINE_COUNT lines, $FILE_SIZE)${NC}"
fi

# Get UI pod name
echo -e "${GREEN}📦 Finding oats-ui pod...${NC}"
UI_POD=$(kubectl get pods -l app=oats-ui -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$UI_POD" ]; then
    echo -e "${RED}❌ No oats-ui pod found${NC}"
else
    echo -e "${GREEN}✓ Found UI pod: $UI_POD${NC}"
    echo -e "${YELLOW}Downloading UI logs...${NC}"
    kubectl logs "$UI_POD" --tail=10000 > "$LOGS_DIR/ui.log" 2>&1
    LINE_COUNT=$(wc -l < "$LOGS_DIR/ui.log" | tr -d ' ')
    FILE_SIZE=$(du -h "$LOGS_DIR/ui.log" | cut -f1)
    echo -e "${GREEN}✓ UI logs saved to $LOGS_DIR/ui.log ($LINE_COUNT lines, $FILE_SIZE)${NC}"
fi

echo ""
echo -e "${GREEN}✅ Log download complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Logs location: ${YELLOW}$LOGS_DIR${NC}"
if [ -f "$LOGS_DIR/agent.log" ] || [ -f "$LOGS_DIR/ui.log" ]; then
    ls -lh "$LOGS_DIR"/*.log 2>/dev/null | awk '{print "  - " $9 " (" $5 ")"}'
fi
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# If logs are not in /logs, provide instructions
if [ "$LOGS_DIR" != "/logs" ]; then
    echo ""
    echo -e "${YELLOW}Note: To save directly to /logs, run with sudo:${NC}"
    echo -e "  sudo LOGS_DIR=/logs $0"
fi
