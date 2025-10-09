# OATS Infrastructure - Kubernetes Manifests

Kubernetes configuration for deploying OATS Cloud components.

## Directory Structure

```
infra/
├── base/                          # Base K8s manifests
│   ├── backend-api-deployment.yaml  # Backend API deployment & service
│   ├── rbac.yaml                    # RBAC roles and service accounts
│   └── secrets.yaml                 # Secrets template (DO NOT commit real secrets)
└── README.md                       # This file
```

## Components

### Backend API (`backend-api-deployment.yaml`)
- FastAPI server for managing agent jobs
- Creates Kubernetes Jobs for agent execution
- Exposes REST API for job management
- Runs as a Deployment with 2 replicas

### RBAC (`rbac.yaml`)
- **Backend API ServiceAccount**: Permissions to manage Jobs and read Pod logs
- **Agent ServiceAccount**: Limited read-only permissions for diagnostics
- Follows principle of least privilege

### Secrets (`secrets.yaml`)
- Template for LLM API keys and configuration
- **IMPORTANT**: Use Kubernetes secrets management in production
- Consider using: sealed-secrets, external-secrets, or vault

## Deployment

### Prerequisites
- Kubernetes cluster (1.24+)
- kubectl configured
- Docker images built and pushed to registry

### Quick Start

1. **Build and push images**:
```bash
# Build backend API
cd services/backend-api
docker build -t your-registry/oats-backend-api:latest .
docker push your-registry/oats-backend-api:latest

# Build agent
cd services/agent
docker build -t your-registry/oats-agent:latest .
docker push your-registry/oats-agent:latest
```

2. **Update secrets with real values**:
```bash
# Create a copy and edit with real values
cp infra/base/secrets.yaml infra/base/secrets.local.yaml
# Edit secrets.local.yaml with your API keys
# DO NOT commit secrets.local.yaml (it's in .gitignore)

kubectl apply -f infra/base/secrets.local.yaml
```

3. **Deploy RBAC and backend API**:
```bash
kubectl apply -f infra/base/rbac.yaml
kubectl apply -f infra/base/backend-api-deployment.yaml
```

4. **Verify deployment**:
```bash
kubectl get pods -l app=oats-backend-api
kubectl logs -l app=oats-backend-api
```

### Testing

Test the API:
```bash
# Port forward to access API
kubectl port-forward svc/oats-backend-api 8000:8000

# Create a test job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"goal": "Test agent execution", "max_turns": 5}'

# Check job status
curl http://localhost:8000/api/v1/jobs/<job-id>
```

## Environment-Specific Configuration

For different environments (dev, staging, prod), use Kustomize or Helm:

### Using Kustomize (Recommended)
```bash
# Create overlays for different environments
mkdir -p infra/overlays/dev
mkdir -p infra/overlays/prod

# Deploy to dev
kubectl apply -k infra/overlays/dev

# Deploy to prod
kubectl apply -k infra/overlays/prod
```

### Using Helm
```bash
# TODO: Create Helm chart in future iteration
helm install oats ./infra/helm/oats --values values-prod.yaml
```

## Security Considerations

1. **Secrets Management**:
   - Never commit real secrets to git
   - Use Kubernetes secrets encryption at rest
   - Consider external secret management (Vault, AWS Secrets Manager, etc.)

2. **RBAC**:
   - Backend API has minimal permissions (only Job management)
   - Agent ServiceAccount has read-only access for diagnostics
   - Review and adjust permissions based on your security requirements

3. **Network Policies**:
   - TODO: Add NetworkPolicy manifests to restrict pod communication
   - Isolate agent jobs from sensitive resources

4. **Pod Security**:
   - TODO: Add PodSecurityPolicy or Pod Security Standards
   - Run containers as non-root
   - Use read-only root filesystems where possible

## Monitoring & Observability

TODO: Add monitoring configuration
- Prometheus ServiceMonitor for metrics
- Grafana dashboards
- Log aggregation (Loki, Elasticsearch)
- Distributed tracing (Jaeger)

## Troubleshooting

### Backend API not starting
```bash
kubectl describe pod -l app=oats-backend-api
kubectl logs -l app=oats-backend-api --tail=50
```

### Agent jobs failing
```bash
# List recent jobs
kubectl get jobs -l app=oats-agent

# Check job logs
kubectl logs job/<job-name>

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp
```

### Permission issues
```bash
# Verify service account
kubectl get serviceaccount oats-backend-api

# Check role bindings
kubectl get rolebinding oats-backend-api-job-manager -o yaml
```

## Next Steps

1. **Phase 1 (Current)**: Backend API + Agent containerization
2. **Phase 2**: Add monitoring, logging, and alerting
3. **Phase 3**: Frontend UI deployment
4. **Phase 4**: Multi-cluster support, HA setup

## Contributing

When adding new K8s resources:
1. Add to appropriate directory (base/ or overlays/)
2. Update this README
3. Test in dev environment first
4. Follow Kubernetes best practices
