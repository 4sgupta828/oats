#!/bin/bash
# Quick script to restart pods without rebuilding images
# Usage: ./scripts/restart-pods.sh [backend|ui|all]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

restart_backend() {
    log_info "Restarting backend pods..."
    kubectl rollout restart deployment/oats-backend-api
    kubectl rollout status deployment/oats-backend-api --timeout=60s
    log_info "Backend pods restarted!"
}

restart_ui() {
    log_info "Restarting UI pods..."
    kubectl rollout restart deployment/oats-ui
    kubectl rollout status deployment/oats-ui --timeout=60s
    log_info "UI pods restarted!"
}

component=${1:-all}

case $component in
    backend)
        restart_backend
        ;;
    ui)
        restart_ui
        ;;
    all)
        restart_backend
        restart_ui
        ;;
    *)
        echo "Usage: $0 [backend|ui|all]"
        exit 1
        ;;
esac

log_info ""
log_info "Pod status:"
kubectl get pods -l 'app in (oats-backend-api,oats-ui)'
