# Makefile for OATS SRE Co-Pilot

# --- Configuration ---
# Replace with your container registry (e.g., docker.io/your-username, gcr.io/your-project)
REGISTRY ?= your-registry
BACKEND_IMG := $(REGISTRY)/oats-backend-api
UI_IMG := $(REGISTRY)/oats-ui
TAG ?= latest
DOCKER_PLATFORM ?= linux/amd64

# --- Docker Build Commands ---

# Build the backend API container image (includes embedded agent)
.PHONY: build-backend
build-backend:
	@echo "Building Backend API image: $(BACKEND_IMG):$(TAG)..."
	@docker build --platform $(DOCKER_PLATFORM) -t $(BACKEND_IMG):$(TAG) -f ./services/backend-api/Dockerfile .

# Build the UI image
.PHONY: build-ui
build-ui:
	@echo "Building UI image: $(UI_IMG):$(TAG)..."
	@docker build --platform $(DOCKER_PLATFORM) -t $(UI_IMG):$(TAG) -f ./services/ui/Dockerfile ./services/ui

# Build backend for cloud (force linux/amd64)
.PHONY: build-backend-cloud
build-backend-cloud:
	@echo "Building Backend API image for cloud: $(BACKEND_IMG):$(TAG)..."
	@docker build --platform linux/amd64 -t $(BACKEND_IMG):$(TAG) -f ./services/backend-api/Dockerfile .

# Build UI for cloud (force linux/amd64)
.PHONY: build-ui-cloud
build-ui-cloud:
	@echo "Building UI image for cloud: $(UI_IMG):$(TAG)..."
	@docker build --platform linux/amd64 -t $(UI_IMG):$(TAG) -f ./services/ui/Dockerfile ./services/ui

# Build all images for cloud (force linux/amd64)
.PHONY: build-cloud
build-cloud: build-backend-cloud build-ui-cloud
	@echo "All cloud images built successfully."

# Build all images
.PHONY: build
build: build-backend build-ui
	@echo "All images built successfully."

# --- Docker Push Commands (Optional, for remote clusters) ---

# Push the backend image to the registry
.PHONY: push-backend
push-backend:
	@echo "Pushing $(BACKEND_IMG):$(TAG)..."
	@docker push $(BACKEND_IMG):$(TAG)

# Push the UI image to the registry
.PHONY: push-ui
push-ui:
	@echo "Pushing $(UI_IMG):$(TAG)..."
	@docker push $(UI_IMG):$(TAG)

# Push all images
.PHONY: push
push: push-backend push-ui
	@echo "All images pushed successfully."

# --- Kubernetes Deployment Commands ---

# Apply all base infrastructure manifests (local k8s - uses local images)
.PHONY: deploy
deploy:
	@echo "Deploying OATS infrastructure to Kubernetes (local mode)..."
	@kubectl apply -f ./infra/base/secrets.yaml
	@kubectl apply -f ./infra/base/rbac.yaml
	@kubectl apply -f ./infra/base/backend-api-service.yaml

	@echo "Deploying Backend API..."
	@sed -e 's|image: .*oats-backend-api.*|image: $(BACKEND_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Never|' \
	     ./infra/base/backend-api-deployment.yaml | kubectl apply -f -

	@echo "Deploying UI..."
	@kubectl apply -f ./infra/base/ui-service.yaml
	@sed -e 's|image: .*oats-ui.*|image: $(UI_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Never|' \
	     ./infra/base/ui-deployment.yaml | kubectl apply -f -

	@echo "Deployment complete."

# Deploy to cloud k8s (pulls from registry)
.PHONY: deploy-cloud
deploy-cloud:
	@echo "Deploying OATS infrastructure to Cloud Kubernetes..."
	@kubectl apply -f ./infra/base/rbac.yaml
	@kubectl apply -f ./infra/base/backend-api-service.yaml

	@echo "Deploying Backend API..."
	@sed -e 's|image: .*oats-backend-api.*|image: $(BACKEND_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Always|' \
	     ./infra/base/backend-api-deployment.yaml | kubectl apply -f -

	@echo "Waiting for backend service to get LoadBalancer URL..."
	@kubectl wait --for=jsonpath='{.status.loadBalancer.ingress}' service/oats-backend-api --timeout=300s || true
	$(eval BACKEND_LB := $(shell kubectl get service oats-backend-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'))
	@echo "Backend LoadBalancer URL: $(BACKEND_LB)"

	@echo "Deploying UI with backend URL..."
	@kubectl apply -f ./infra/base/ui-service.yaml
	@sed -e 's|image: .*oats-ui.*|image: $(UI_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Always|' \
	     -e 's|value: "http://localhost:8000"|value: "http://$(BACKEND_LB):8000"|' \
	     ./infra/base/ui-deployment.yaml | kubectl apply -f -

	@echo "Cloud deployment complete."
	@echo "Backend API: http://$(BACKEND_LB):8000"
	@echo "Note: Secrets must be created separately with kubectl create secret"

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

# Refresh k8s pods with latest code (rebuild images + restart)
.PHONY: refresh
refresh:
	@./scripts/refresh-k8s.sh all

# Refresh only backend
.PHONY: refresh-backend
refresh-backend:
	@./scripts/refresh-k8s.sh backend

# Refresh only UI
.PHONY: refresh-ui
refresh-ui:
	@./scripts/refresh-k8s.sh ui

# Deploy updated backend to cloud (build + push + restart)
.PHONY: deploy-backend-cloud
deploy-backend-cloud: build-backend-cloud push-backend
	@echo "Restarting backend deployment..."
	@kubectl rollout restart deployment/oats-backend-api
	@kubectl rollout status deployment/oats-backend-api --timeout=120s
	@echo "Backend deployment complete!"

# Deploy updated UI to cloud (build + push + restart)
.PHONY: deploy-ui-cloud
deploy-ui-cloud: build-ui-cloud push-ui
	@echo "Restarting UI deployment..."
	@kubectl rollout restart deployment/oats-ui
	@kubectl rollout status deployment/oats-ui --timeout=120s
	@echo "UI deployment complete!"

# Quick restart pods without rebuilding
.PHONY: restart
restart:
	@./scripts/restart-pods.sh all

.PHONY: help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build               Build all Docker images (for local use)"
	@echo "  build-cloud         Build all Docker images for cloud (linux/amd64)"
	@echo "  deploy              Deploy all resources to local Kubernetes"
	@echo "  deploy-cloud        Deploy all resources to cloud Kubernetes (EKS/GKE/AKS)"
	@echo "  deploy-backend-cloud Deploy updated backend to cloud (build+push+restart)"
	@echo "  deploy-ui-cloud     Deploy updated UI to cloud (build+push+restart)"
	@echo "  clean               Remove all deployed resources from Kubernetes"
	@echo "  push                Push all images to the configured registry"
	@echo "  refresh             Rebuild images and refresh all pods"
	@echo "  refresh-backend     Rebuild and refresh only backend"
	@echo "  refresh-ui          Rebuild and refresh only UI"
	@echo "  restart             Restart pods without rebuilding"
	@echo "  help                Show this help message"
	@echo ""
	@echo "Cloud Deployment Quick Start:"
	@echo "  Initial setup: export REGISTRY=911167909198.dkr.ecr.us-west-2.amazonaws.com"
	@echo "  Full deployment: make build-cloud && make push && make deploy-cloud"
	@echo ""
	@echo "Update existing cloud deployment:"
	@echo "  Backend only: make deploy-backend-cloud"
	@echo "  UI only:      make deploy-ui-cloud"