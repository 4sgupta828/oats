# OATS Cloud Quick Start

This is a TL;DR version for deploying OATS to AWS EKS. For full details, see [AWS_DEPLOYMENT.md](./AWS_DEPLOYMENT.md).

## Prerequisites

```bash
# Install tools
brew install awscli eksctl kubectl  # macOS
# OR follow official docs for Linux

# Configure AWS
aws configure
```

## Option 1: Interactive Script (Easiest)

```bash
# Run the interactive deployment script
./scripts/deploy-aws.sh
```

Follow the menu to:
1. Create ECR repositories
2. Create EKS cluster
3. Build and push images
4. Deploy OATS
5. Or do everything in one go (option 5)

## Option 2: Manual Commands

```bash
# 1. Set environment variables
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# 2. Create ECR repositories
aws ecr create-repository --repository-name oats-backend-api --region $AWS_REGION
aws ecr create-repository --repository-name oats-ui --region $AWS_REGION

# 3. Create EKS cluster (takes ~15 minutes)
eksctl create cluster \
  --name oats-dev \
  --region $AWS_REGION \
  --nodes 2 \
  --node-type t3.medium

# 4. Build and push images
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $REGISTRY

REGISTRY=$REGISTRY make build push

# 5. Create secrets
kubectl create secret generic oats-api-keys \
  --from-literal=openai-api-key="$OPENAI_API_KEY" \
  --from-literal=anthropic-api-key="${ANTHROPIC_API_KEY:-dummy}"

# 6. Deploy to EKS
REGISTRY=$REGISTRY make deploy-cloud

# 7. Verify
kubectl get pods
```

## Access Your Application

### Option A: LoadBalancer (costs extra)

```bash
# Enable LoadBalancer
kubectl patch service oats-backend-api-service -p '{"spec":{"type":"LoadBalancer"}}'
kubectl patch service oats-ui-service -p '{"spec":{"type":"LoadBalancer"}}'

# Get URLs
kubectl get service oats-backend-api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
kubectl get service oats-ui-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Option B: Port Forwarding (free)

```bash
kubectl port-forward service/oats-backend-api-service 8000:8000 &
kubectl port-forward service/oats-ui-service 8080:8080 &

# Access at:
# Backend: http://localhost:8000/docs
# UI: http://localhost:8080
```

## Test the Agent

```bash
# Get backend URL
BACKEND_URL=$(kubectl get service oats-backend-api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Or use localhost if port-forwarding
BACKEND_URL=localhost

# Create a job
curl -X POST http://$BACKEND_URL:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Check the health of the oats-backend-api pod in the default namespace",
    "max_turns": 10
  }'

# The agent will now investigate itself running in the cloud!
```

## Agent Self-Operation

Your agent now runs **inside** EKS and can:

- Query Kubernetes API for pod status, logs, metrics
- Diagnose cluster issues (network, DNS, resource constraints)
- Check service health across the cluster
- Investigate itself and other OATS components
- Self-heal by restarting unhealthy pods

Example investigations:
- "Why is the oats-backend-api pod crashing?"
- "Diagnose high memory usage in the default namespace"
- "Check if CoreDNS is working properly"
- "Investigate intermittent connection timeouts"

## Daily Operations

```bash
# View logs
kubectl logs -l app=oats-backend-api -f

# Update code
REGISTRY=$REGISTRY make build push
kubectl rollout restart deployment/oats-backend-api

# Check status
kubectl get pods
kubectl top nodes
kubectl top pods

# Scale nodes (for cost savings)
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=0  # Stop
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=2  # Start
```

## Cost Optimization

**Estimated costs (us-west-2):**
- 2x t3.medium nodes: ~$60/month (24/7)
- 1x EKS control plane: $73/month
- **Total: ~$133/month**

**Reduce costs:**
```bash
# Stop when not in use (saves ~$60/month)
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=0

# Or delete completely
eksctl delete cluster --name=oats-dev --region=$AWS_REGION
```

## Cleanup

```bash
# Delete everything
./scripts/deploy-aws.sh  # Choose option 8

# Or manually:
eksctl delete cluster --name=oats-dev --region=$AWS_REGION
aws ecr delete-repository --repository-name oats-backend-api --region=$AWS_REGION --force
aws ecr delete-repository --repository-name oats-ui --region=$AWS_REGION --force
```

## Troubleshooting

### Pods not starting
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

### Can't pull images from ECR
```bash
# Re-authenticate
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $REGISTRY

# Verify images exist
aws ecr describe-images --repository-name oats-backend-api
```

### RBAC permission issues
```bash
# Check ServiceAccount
kubectl get serviceaccount oats-backend -o yaml

# Check if pods use the ServiceAccount
kubectl get pod <pod-name> -o yaml | grep serviceAccount
```

## Environment Variables Reference

```bash
# Required for cloud deployment
export AWS_REGION=us-west-2                          # Your AWS region
export AWS_ACCOUNT_ID=123456789012                   # Your AWS account
export REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
export OPENAI_API_KEY=sk-...                        # Your OpenAI key
export ANTHROPIC_API_KEY=sk-ant-...                 # Optional

# Cluster configuration (optional, has defaults)
export CLUSTER_NAME=oats-dev                        # Default: oats-dev
export NODE_COUNT=2                                 # Default: 2
export INSTANCE_TYPE=t3.medium                      # Default: t3.medium
```

## Next Steps

1. **Set up CI/CD**: Automate deployment with GitHub Actions
2. **Add monitoring**: CloudWatch Container Insights, Prometheus, Grafana
3. **Enable autoscaling**: Cluster Autoscaler for dynamic node scaling
4. **Add Ingress**: AWS ALB Ingress Controller for better routing
5. **Persistent storage**: EBS volumes or S3 for agent results
6. **Multi-environment**: Separate dev/staging/prod clusters

---

**Full documentation:** [AWS_DEPLOYMENT.md](./AWS_DEPLOYMENT.md)
