#!/bin/bash
# Script to rebuild images and refresh Kubernetes pods
# Usage: ./scripts/refresh-k8s.sh [backend|ui|all]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default registry
REGISTRY=${REGISTRY:-oats}

# Function to print colored output
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi
}

# Function to check if docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "docker not found. Please install docker."
        exit 1
    fi
}

# Function to rebuild backend image
rebuild_backend() {
    log_info "Building backend API image..."
    docker build -t ${REGISTRY}/oats-backend-api:latest -f ./services/backend-api/Dockerfile .

    # Tag with timestamp for version tracking
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    docker tag ${REGISTRY}/oats-backend-api:latest ${REGISTRY}/oats-backend-api:${TIMESTAMP}
    log_info "Backend image built: ${REGISTRY}/oats-backend-api:latest (also tagged as ${TIMESTAMP})"
}

# Function to rebuild UI image
rebuild_ui() {
    log_info "Building UI image..."
    docker build -t ${REGISTRY}/oats-ui:latest -f ./services/ui/Dockerfile .

    # Tag with timestamp for version tracking
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    docker tag ${REGISTRY}/oats-ui:latest ${REGISTRY}/oats-ui:${TIMESTAMP}
    log_info "UI image built: ${REGISTRY}/oats-ui:latest (also tagged as ${TIMESTAMP})"
}

# Function to restart backend pods
restart_backend() {
    log_info "Restarting backend API pods..."

    # Update deployment to use the new image
    kubectl set image deployment/oats-backend-api backend-api=${REGISTRY}/oats-backend-api:latest

    # Force restart by deleting pods
    kubectl rollout restart deployment/oats-backend-api

    log_info "Waiting for backend pods to be ready..."
    kubectl rollout status deployment/oats-backend-api --timeout=120s

    log_info "Backend pods restarted successfully!"
}

# Function to restart UI pods
restart_ui() {
    log_info "Restarting UI pods..."

    # Update deployment to use the new image
    kubectl set image deployment/oats-ui ui=${REGISTRY}/oats-ui:latest

    # Force restart by deleting pods
    kubectl rollout restart deployment/oats-ui

    log_info "Waiting for UI pods to be ready..."
    kubectl rollout status deployment/oats-ui --timeout=120s

    log_info "UI pods restarted successfully!"
}

# Function to load image into kind cluster (if using kind)
load_to_kind() {
    local image=$1
    if kubectl config current-context | grep -q "kind"; then
        log_info "Detected kind cluster, loading image: ${image}"
        kind load docker-image ${image}
    fi
}

# Main script
main() {
    local component=${1:-all}

    log_info "=== OATS Kubernetes Refresh Script ==="
    log_info "Component: ${component}"
    log_info "Registry: ${REGISTRY}"
    log_info ""

    # Check prerequisites
    check_kubectl
    check_docker

    case $component in
        backend)
            rebuild_backend
            load_to_kind "${REGISTRY}/oats-backend-api:latest"
            restart_backend
            ;;
        ui)
            rebuild_ui
            load_to_kind "${REGISTRY}/oats-ui:latest"
            restart_ui
            ;;
        all)
            rebuild_backend
            rebuild_ui
            load_to_kind "${REGISTRY}/oats-backend-api:latest"
            load_to_kind "${REGISTRY}/oats-ui:latest"
            restart_backend
            restart_ui
            ;;
        *)
            log_error "Invalid component: ${component}"
            echo "Usage: $0 [backend|ui|all]"
            exit 1
            ;;
    esac

    log_info ""
    log_info "=== Refresh Complete! ==="
    log_info "Checking pod status..."
    kubectl get pods -l 'app in (oats-backend-api,oats-ui)'

    log_info ""
    log_info "Access URLs:"
    log_info "  UI:          http://localhost:8080"
    log_info "  Backend API: http://localhost:8000/docs"
}

# Run main function
main "$@"
