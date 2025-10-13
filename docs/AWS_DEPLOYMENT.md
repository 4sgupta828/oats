# AWS EKS Deployment Guide - Minimal Dev Setup

This guide walks you through deploying OATS to AWS EKS with minimal setup for development purposes.

## Prerequisites

1. **AWS CLI** installed and configured:
   ```bash
   aws --version
   aws configure  # Set up your credentials
   ```

2. **eksctl** installed:
   ```bash
   # macOS
   brew tap weaveworks/tap
   brew install weaveworks/tap/eksctl

   # Linux
   curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
   sudo mv /tmp/eksctl /usr/local/bin
   ```

3. **kubectl** already installed (you have this)

4. **AWS Account** with appropriate permissions

## Step 1: Create ECR Repositories

Create two ECR repositories for your container images:

```bash
# Set your AWS region
export AWS_REGION=us-west-2  # Change to your preferred region
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create ECR repositories
aws ecr create-repository --repository-name oats-backend-api --region $AWS_REGION
aws ecr create-repository --repository-name oats-ui --region $AWS_REGION

# Get ECR login (authenticate Docker)
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Set your registry URL
export REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
echo "Your registry: $REGISTRY"
```

## Step 2: Create Minimal EKS Cluster

Create a minimal 2-node cluster (suitable for dev):

```bash
# Create cluster config
cat > /tmp/oats-cluster.yaml <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: oats-dev
  region: $AWS_REGION

# Minimal node group for dev
nodeGroups:
  - name: oats-nodes
    instanceType: t3.medium  # 2 vCPU, 4GB RAM - sufficient for dev
    desiredCapacity: 2
    minSize: 1
    maxSize: 3
    volumeSize: 30
    ssh:
      allow: false
    iam:
      withAddonPolicies:
        imageBuilder: true
        autoScaler: true
        cloudWatch: true

# Enable basic addons
addons:
  - name: vpc-cni
  - name: coredns
  - name: kube-proxy
EOF

# Create the cluster (takes ~15-20 minutes)
eksctl create cluster -f /tmp/oats-cluster.yaml
```

**Cost Estimate**: ~$60-80/month for 2x t3.medium instances running 24/7

**To reduce costs**:
- Stop cluster when not in use: `eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=0`
- Start again: `eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=2`
- Or delete entirely: `eksctl delete cluster --name=oats-dev`

## Step 3: Configure kubectl Context

```bash
# Update kubeconfig (eksctl does this automatically, but verify)
aws eks update-kubeconfig --name oats-dev --region $AWS_REGION

# Verify connection
kubectl get nodes
# You should see 2 nodes in Ready state
```

## Step 4: Build and Push Images to ECR

```bash
# From your OATS project root
cd /Users/sgupta/oats

# Build images
REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com make build

# Push to ECR
REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com make push
```

## Step 5: Update Kubernetes Secrets

Create secrets with your API keys:

```bash
# Create secrets for OpenAI/Anthropic API keys
kubectl create secret generic oats-api-keys \
  --from-literal=openai-api-key="$OPENAI_API_KEY" \
  --from-literal=anthropic-api-key="${ANTHROPIC_API_KEY:-dummy}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Step 6: Deploy OATS to EKS

```bash
# Update image pull policy for cloud deployment
REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com make deploy-cloud

# Or manually:
# 1. Apply infrastructure
kubectl apply -f ./infra/base/rbac.yaml
kubectl apply -f ./infra/base/backend-api-service.yaml
kubectl apply -f ./infra/base/ui-service.yaml

# 2. Deploy backend with ECR image
sed -e "s|image: .*oats-backend-api.*|image: $REGISTRY/oats-backend-api:latest|" \
    -e "s|imagePullPolicy:.*|imagePullPolicy: Always|" \
    ./infra/base/backend-api-deployment.yaml | kubectl apply -f -

# 3. Deploy UI with ECR image
sed -e "s|image: .*oats-ui.*|image: $REGISTRY/oats-ui:latest|" \
    -e "s|imagePullPolicy:.*|imagePullPolicy: Always|" \
    ./infra/base/ui-deployment.yaml | kubectl apply -f -
```

## Step 7: Access Your Application

### Option A: LoadBalancer (Simplest for Dev)

Update your services to use LoadBalancer:

```bash
# Patch backend service
kubectl patch service oats-backend-api-service -p '{"spec":{"type":"LoadBalancer"}}'

# Patch UI service
kubectl patch service oats-ui-service -p '{"spec":{"type":"LoadBalancer"}}'

# Get LoadBalancer URLs (may take 2-3 minutes to provision)
echo "Backend API:"
kubectl get service oats-backend-api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

echo "UI:"
kubectl get service oats-ui-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

Access via:
- Backend API: `http://<backend-lb-url>:8000/docs`
- UI: `http://<ui-lb-url>:8080`

### Option B: Port Forwarding (No LoadBalancer costs)

```bash
# Forward backend API
kubectl port-forward service/oats-backend-api-service 8000:8000 &

# Forward UI
kubectl port-forward service/oats-ui-service 8080:8080 &

# Access locally
# Backend API: http://localhost:8000/docs
# UI: http://localhost:8080
```

## Step 8: Verify Deployment

```bash
# Check pods
kubectl get pods

# Check logs
kubectl logs -l app=oats-backend-api -f

# Test the API
BACKEND_URL=$(kubectl get service oats-backend-api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://$BACKEND_URL:8000/health
```

## Agent Self-Operation in Cloud

Your OATS agent now runs **inside** the EKS cluster and has access to:

1. **Kubernetes API** via the ServiceAccount with RBAC permissions (infra/base/rbac.yaml)
2. **Cloud resources** through IAM roles (can be extended)
3. **Cluster networking** to diagnose services

### Example: Agent Investigating Itself

When you create a job:
```bash
curl -X POST http://$BACKEND_URL:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Why is the oats-backend-api pod using high memory?",
    "max_turns": 10
  }'
```

The agent can:
- Query Kubernetes API for pod metrics
- Check logs of other pods
- Analyze resource constraints
- Diagnose network issues
- Self-heal by restarting pods or adjusting resources

## Updating Your Application

```bash
# Make code changes locally

# Rebuild and push
REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com make build push

# Refresh pods
kubectl rollout restart deployment/oats-backend-api
kubectl rollout restart deployment/oats-ui

# Or use your refresh script (update for cloud)
make refresh
```

## Monitoring and Logs

```bash
# View backend logs
kubectl logs -l app=oats-backend-api --tail=100 -f

# View UI logs
kubectl logs -l app=oats-ui --tail=100 -f

# View all pods
kubectl get pods --watch

# Describe a pod for troubleshooting
kubectl describe pod <pod-name>
```

## Cost Optimization

### Shut Down Cluster When Not in Use

```bash
# Stop nodes (saves ~90% of costs)
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=0 --region=$AWS_REGION

# Start again
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=2 --region=$AWS_REGION
```

### Scheduled Shutdown (Optional)

Create a Lambda function to stop/start the cluster on a schedule:
- Stop: 6 PM weekdays, all day weekends
- Start: 9 AM weekdays
- Saves ~70% of compute costs for dev environment

### Even Cheaper: Spot Instances

For non-critical dev work, use Spot instances (~70% discount):

```yaml
# In cluster config
nodeGroups:
  - name: oats-nodes-spot
    instanceType: t3.medium
    desiredCapacity: 2
    minSize: 1
    maxSize: 3
    spot: true  # Add this line
```

## Cleanup / Teardown

```bash
# Delete Kubernetes resources
kubectl delete -f ./infra/base/

# Delete the EKS cluster (saves all costs)
eksctl delete cluster --name=oats-dev --region=$AWS_REGION

# Delete ECR repositories (optional - preserves images if recreating)
aws ecr delete-repository --repository-name oats-backend-api --region=$AWS_REGION --force
aws ecr delete-repository --repository-name oats-ui --region=$AWS_REGION --force
```

## Troubleshooting

### Pods not starting
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

### ImagePullBackOff errors
```bash
# Verify ECR authentication
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Check if images exist in ECR
aws ecr describe-images --repository-name oats-backend-api --region $AWS_REGION
```

### Can't access LoadBalancer
```bash
# Check security groups (EKS creates them automatically)
kubectl describe service oats-backend-api-service

# Check if LoadBalancer is provisioned
kubectl get service oats-backend-api-service -o wide
```

### RBAC Permission Issues
```bash
# Verify ServiceAccount is attached
kubectl get pod <pod-name> -o yaml | grep serviceAccount

# Check RBAC permissions
kubectl auth can-i --list --as=system:serviceaccount:default:oats-backend
```

## Next Steps

1. **Set up persistent storage** for agent results (EBS volumes or S3)
2. **Add CloudWatch integration** for deeper observability
3. **Configure auto-scaling** for production workloads
4. **Set up CI/CD** with GitHub Actions deploying to EKS
5. **Add Ingress Controller** (AWS ALB) for better routing
6. **Enable cluster autoscaling** for cost optimization

## Quick Reference

```bash
# Environment variables to set
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export REGISTRY=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Common commands
make build push deploy-cloud      # Build, push, deploy
kubectl get pods                   # Check pod status
kubectl logs -l app=oats-backend-api -f  # View logs
kubectl rollout restart deployment/oats-backend-api  # Restart
```

## Support

- AWS EKS Docs: https://docs.aws.amazon.com/eks/
- eksctl Docs: https://eksctl.io/
- Kubernetes RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
