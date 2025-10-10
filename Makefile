# Makefile for OATS SRE Co-Pilot

# --- Configuration ---
# Replace with your container registry (e.g., docker.io/your-username, gcr.io/your-project)
REGISTRY ?= your-registry
AGENT_IMG := $(REGISTRY)/oats-agent
BACKEND_IMG := $(REGISTRY)/oats-backend-api
UI_IMG := $(REGISTRY)/oats-ui # New: UI image variable
TAG ?= latest

# --- Docker Build Commands ---

# Build the SRE agent container image
.PHONY: build-agent
build-agent:
	@echo "Building OATS Agent image: $(AGENT_IMG):$(TAG)..."
	@docker build -t $(AGENT_IMG):$(TAG) -f ./services/agent/Dockerfile .

# Build the backend API container image
.PHONY: build-backend
build-backend:
	@echo "Building Backend API image: $(BACKEND_IMG):$(TAG)..."
	@docker build -t $(BACKEND_IMG):$(TAG) -f ./services/backend-api/Dockerfile .

# New: Target to build the UI image
.PHONY: build-ui
build-ui:
	@echo "Building UI image: $(UI_IMG):$(TAG)..."
	@docker build -t $(UI_IMG):$(TAG) -f ./services/ui/Dockerfile .

# Updated: 'build' now includes the UI
.PHONY: build
build: build-agent build-backend build-ui
	@echo "All images built successfully."

# --- Docker Push Commands (Optional, for remote clusters) ---

# Push the agent image to the registry
.PHONY: push-agent
push-agent:
	@echo "Pushing $(AGENT_IMG):$(TAG)..."
	@docker push $(AGENT_IMG):$(TAG)

# Push the backend image to the registry
.PHONY: push-backend
push-backend:
	@echo "Pushing $(BACKEND_IMG):$(TAG)..."
	@docker push $(BACKEND_IMG):$(TAG)

# Push all images
.PHONY: push
push: push-agent push-backend
	@echo "All images pushed successfully."

# --- Kubernetes Deployment Commands ---

# Apply all base infrastructure manifests
.PHONY: deploy
deploy:
	@echo "Deploying OATS infrastructure to Kubernetes..."
	@kubectl apply -f ./infra/base/secrets.yaml
	@kubectl apply -f ./infra/base/rbac.yaml
	
	@echo "Deploying Backend API..."
	@sed 's|your-repo/oats-backend-api:latest|$(BACKEND_IMG):$(TAG)|' ./infra/base/backend-api-deployment.yaml | kubectl apply -f -
	
	@echo "Deploying UI..." # New: Deploying the UI service and deployment
	@kubectl apply -f ./infra/base/ui-service.yaml
	@sed 's|your-repo/oats-ui:latest|$(UI_IMG):$(TAG)|' ./infra/base/ui-deployment.yaml | kubectl apply -f -
	
	@echo "Deployment complete."

# Delete all deployed resources
.PHONY: clean
clean:
	@echo "Cleaning up OATS infrastructure from Kubernetes..."
	@kubectl delete deployment oats-backend-api --ignore-not-found
	@kubectl delete deployment oats-ui --ignore-not-found # New: Clean up UI deployment
	@kubectl delete service oats-ui-service --ignore-not-found # New: Clean up UI service
	@kubectl delete -f ./infra/base/rbac.yaml --ignore-not-found
	@kubectl delete -f ./infra/base/secrets.yaml --ignore-not-found
	@echo "Cleanup complete."

# --- Utility Commands ---

.PHONY: help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build          Build all Docker images"
	@echo "  deploy         Deploy all resources to the current kubectl context"
	@echo "  clean          Remove all deployed resources from Kubernetes"
	@echo "  push           Push all images to the configured registry"
	@echo "  help           Show this help message"