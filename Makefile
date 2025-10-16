# Makefile for OATS - Cloud Deployment

# --- Configuration ---
REGISTRY ?= 911167909198.dkr.ecr.us-west-2.amazonaws.com
BACKEND_IMG := $(REGISTRY)/oats-backend-api
UI_IMG := $(REGISTRY)/oats-ui
TAG ?= latest
AWS_REGION ?= us-west-2

# --- Main Commands ---

# Authenticate with ECR
.PHONY: ecr-login
ecr-login:
	@echo "🔐 Authenticating with ECR..."
	@aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(REGISTRY)
	@echo "✅ ECR authentication successful!"

# Deploy backend to cloud (build + push + restart)
.PHONY: deploy-backend
deploy-backend: ecr-login
	@echo "🔨 Building backend for cloud (linux/amd64)..."
	@docker build --platform linux/amd64 -t $(BACKEND_IMG):$(TAG) -f ./services/backend-api/Dockerfile .
	@echo "📤 Pushing to ECR..."
	@docker push $(BACKEND_IMG):$(TAG)
	@echo "🔄 Updating deployment image..."
	@kubectl set image deployment/oats-backend-api backend-api=$(BACKEND_IMG):$(TAG)
	@kubectl patch deployment oats-backend-api -p '{"spec":{"template":{"spec":{"containers":[{"name":"backend-api","imagePullPolicy":"Always"}]}}}}'
	@kubectl rollout status deployment/oats-backend-api --timeout=120s
	@echo "✅ Backend deployed successfully!"

# Deploy UI to cloud (build + push + restart)
.PHONY: deploy-ui
deploy-ui: ecr-login
	@echo "🔨 Building UI for cloud (linux/amd64)..."
	@docker build --platform linux/amd64 -t $(UI_IMG):$(TAG) -f ./services/ui/Dockerfile ./services/ui
	@echo "📤 Pushing to ECR..."
	@docker push $(UI_IMG):$(TAG)
	@echo "🔄 Updating deployment image..."
	@kubectl set image deployment/oats-ui ui=$(UI_IMG):$(TAG)
	@kubectl patch deployment oats-ui -p '{"spec":{"template":{"spec":{"containers":[{"name":"ui","imagePullPolicy":"Always"}]}}}}'
	@kubectl rollout status deployment/oats-ui --timeout=120s
	@echo "✅ UI deployed successfully!"

# Deploy both backend and UI
.PHONY: deploy-all
deploy-all: deploy-backend deploy-ui
	@echo "✅ Full deployment complete!"

# Initial cloud setup (creates all resources)
.PHONY: setup
setup: ecr-login
	@echo "🚀 Setting up OATS infrastructure in cloud..."
	@kubectl apply -f ./infra/base/rbac.yaml
	@kubectl apply -f ./infra/base/backend-api-service.yaml
	@kubectl apply -f ./infra/base/ui-service.yaml

	@echo "🔨 Building images..."
	@docker build --platform linux/amd64 -t $(BACKEND_IMG):$(TAG) -f ./services/backend-api/Dockerfile .
	@docker build --platform linux/amd64 -t $(UI_IMG):$(TAG) -f ./services/ui/Dockerfile ./services/ui

	@echo "📤 Pushing images to ECR..."
	@docker push $(BACKEND_IMG):$(TAG)
	@docker push $(UI_IMG):$(TAG)

	@echo "🚀 Deploying backend..."
	@sed -e 's|image: .*oats-backend-api.*|image: $(BACKEND_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Always|' \
	     ./infra/base/backend-api-deployment.yaml | kubectl apply -f -

	@echo "⏳ Waiting for backend LoadBalancer..."
	@kubectl wait --for=jsonpath='{.status.loadBalancer.ingress}' service/oats-backend-api --timeout=300s || true
	$(eval BACKEND_LB := $(shell kubectl get service oats-backend-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'))

	@echo "🚀 Deploying UI..."
	@sed -e 's|image: .*oats-ui.*|image: $(UI_IMG):$(TAG)|' \
	     -e 's|imagePullPolicy:.*|imagePullPolicy: Always|' \
	     -e 's|value: "http://localhost:8000"|value: "http://$(BACKEND_LB):8000"|' \
	     ./infra/base/ui-deployment.yaml | kubectl apply -f -

	@echo ""
	@echo "✅ Setup complete!"
	@echo "📍 Backend API: http://$(BACKEND_LB):8000"
	@echo "📍 UI: Check LoadBalancer with: kubectl get svc oats-ui-service"

# Clean up all resources
.PHONY: clean
clean:
	@echo "🗑️  Cleaning up OATS infrastructure..."
	@kubectl delete deployment oats-backend-api oats-ui --ignore-not-found
	@kubectl delete service oats-backend-api oats-ui-service --ignore-not-found
	@kubectl delete -f ./infra/base/rbac.yaml --ignore-not-found
	@echo "✅ Cleanup complete"

# Get service URLs
.PHONY: urls
urls:
	@echo "📍 OATS Service URLs:"
	@echo ""
	@echo "Backend API:"
	@kubectl get service oats-backend-api -o jsonpath='  http://{.status.loadBalancer.ingress[0].hostname}:8000' && echo
	@echo ""
	@echo "UI:"
	@kubectl get service oats-ui-service -o jsonpath='  http://{.status.loadBalancer.ingress[0].hostname}:8080' && echo
	@echo ""

# Show pod status
.PHONY: status
status:
	@echo "📊 OATS Pod Status:"
	@kubectl get pods -l app=oats-backend-api -o wide
	@kubectl get pods -l app=oats-ui -o wide

# Show logs
.PHONY: logs-backend
logs-backend:
	@kubectl logs -l app=oats-backend-api --tail=50 -f

.PHONY: logs-ui
logs-ui:
	@kubectl logs -l app=oats-ui --tail=50 -f

# Help
.PHONY: help
help:
	@echo "OATS Cloud Deployment Commands"
	@echo ""
	@echo "📦 Deployment:"
	@echo "  make deploy-backend    Deploy backend to cloud (build+push+restart)"
	@echo "  make deploy-ui         Deploy UI to cloud (build+push+restart)"
	@echo "  make deploy-all        Deploy both backend and UI"
	@echo ""
	@echo "🚀 Setup:"
	@echo "  make setup             Initial cloud setup (creates all resources)"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  make urls              Show service URLs"
	@echo "  make status            Show pod status"
	@echo "  make logs-backend      Tail backend logs"
	@echo "  make logs-ui           Tail UI logs"
	@echo ""
	@echo "🗑️  Cleanup:"
	@echo "  make clean             Remove all resources"
	@echo ""
	@echo "💡 Examples:"
	@echo "  make deploy-backend    # Update backend only"
	@echo "  make deploy-ui         # Update UI only"
	@echo "  make urls              # Get access URLs"

.DEFAULT_GOAL := help
