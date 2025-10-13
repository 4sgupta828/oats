#!/bin/bash

# Script to download logs from Kubernetes pods running in AWS EKS
# This version writes directly to /logs directory (requires sudo)

set -e

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔍 Fetching logs from AWS EKS cluster...${NC}"

# Always use /logs
LOGS_DIR="/logs"

# Create logs directory if it doesn't exist
if [ ! -d "$LOGS_DIR" ]; then
    echo -e "${YELLOW}Creating $LOGS_DIR directory...${NC}"
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
    chmod 644 "$LOGS_DIR/agent.log"
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
    chmod 644 "$LOGS_DIR/ui.log"
    LINE_COUNT=$(wc -l < "$LOGS_DIR/ui.log" | tr -d ' ')
    FILE_SIZE=$(du -h "$LOGS_DIR/ui.log" | cut -f1)
    echo -e "${GREEN}✓ UI logs saved to $LOGS_DIR/ui.log ($LINE_COUNT lines, $FILE_SIZE)${NC}"
fi

echo ""
echo -e "${GREEN}✅ Log download complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Logs saved to ${YELLOW}/logs${NC}:"
if [ -f "$LOGS_DIR/agent.log" ] || [ -f "$LOGS_DIR/ui.log" ]; then
    ls -lh "$LOGS_DIR"/*.log 2>/dev/null | awk '{print "  - " $9 " (" $5 ")"}'
fi
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
