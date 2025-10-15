#!/bin/bash
# Smart deployment for OATS on AWS EKS - skips completed steps
# Usage: ./DEPLOY.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Colors for status
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
print_skip() { echo -e "${GREEN}[SKIP]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo -e "${GREEN}=========================================="
echo "  OATS Smart AWS Deployment"
echo "  Account: 911167909198"
echo "==========================================${NC}"
echo ""

# Load AWS configuration
source .env.aws

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    print_warn "AWS CLI not configured. Running 'aws configure'..."
    aws configure
fi

# Check if Anthropic API key is set (we use Claude by default)
if [ -z "$ANTHROPIC_API_KEY" ]; then
    print_warn "ANTHROPIC_API_KEY not set"
    read -sp "Enter your Anthropic API key: " ANTHROPIC_API_KEY
    echo ""
    export ANTHROPIC_API_KEY
fi

echo ""
print_info "Deployment configuration:"
echo "  Registry: $REGISTRY"
echo "  Region: $AWS_REGION"
echo "  Cluster: $CLUSTER_NAME"
echo ""

# Function to get service URLs
get_service_urls() {
    local backend_lb=$(kubectl get service oats-backend-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    local ui_lb=$(kubectl get service oats-ui-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    
    if [ -n "$backend_lb" ] && [ -n "$ui_lb" ]; then
        print_info "🌐 Access URLs:"
        echo ""
        echo -e "${GREEN}  Backend API:${NC}"
        echo "    URL: http://${backend_lb}:8000"
        echo "    Docs: http://${backend_lb}:8000/docs"
        echo ""
        echo -e "${GREEN}  UI (Frontend):${NC}"
        echo "    URL: http://${ui_lb}:8080"
        echo ""
        echo -e "${GREEN}  Quick Test Commands:${NC}"
        echo "    # Test backend:"
        echo "    curl http://${backend_lb}:8000/docs"
        echo ""
        echo "    # Test UI:"
        echo "    curl http://${ui_lb}:8080"
        echo ""
        echo -e "${GREEN}  Test Agent Execution:${NC}"
        echo "    curl -X POST http://${backend_lb}:8000/api/v1/executions \\"
        echo "      -H 'Content-Type: application/json' \\"
        echo "      -d '{\"goal\": \"Check health of all pods\", \"max_turns\": 10}'"
        echo ""
    else
        print_warn "LoadBalancer URLs not ready yet. Waiting..."
        sleep 10
        
        # Try again
        backend_lb=$(kubectl get service oats-backend-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
        ui_lb=$(kubectl get service oats-ui-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
        
        if [ -n "$backend_lb" ] && [ -n "$ui_lb" ]; then
            print_info "🌐 Access URLs (after wait):"
            echo ""
            echo -e "${GREEN}  Backend API:${NC} http://${backend_lb}:8000"
            echo -e "${GREEN}  UI (Frontend):${NC} http://${ui_lb}:8080"
            echo ""
        else
            print_warn "LoadBalancer URLs still not ready. You can check manually:"
            echo "  kubectl get services"
            echo ""
            echo "Or use port-forwarding:"
            echo "  kubectl port-forward service/oats-backend-api-service 8000:8000"
            echo "  kubectl port-forward service/oats-ui-service 8080:8080"
            echo ""
        fi
    fi
}

# Function to check if ECR repositories exist
check_ecr_repos() {
    local backend_exists=false
    local ui_exists=false
    
    if aws ecr describe-repositories --repository-names oats-backend-api --region $AWS_REGION >/dev/null 2>&1; then
        backend_exists=true
    fi
    
    if aws ecr describe-repositories --repository-names oats-ui --region $AWS_REGION >/dev/null 2>&1; then
        ui_exists=true
    fi
    
    if $backend_exists && $ui_exists; then
        return 0  # Both exist
    else
        return 1  # At least one missing
    fi
}

# Function to check if EKS cluster exists and has running nodes
check_eks_cluster() {
    # First check if cluster exists
    if ! eksctl get cluster --name $CLUSTER_NAME --region $AWS_REGION >/dev/null 2>&1; then
        return 1  # Cluster doesn't exist
    fi
    
    # Check if cluster has any nodes
    if ! kubectl get nodes --no-headers 2>/dev/null | grep -q Ready; then
        return 1  # Cluster exists but no nodes are ready
    fi
    
    return 0  # Cluster exists and has ready nodes
}

# Function to check if node group exists and has capacity
check_nodegroup_capacity() {
    # Check if jq is available
    if ! command -v jq >/dev/null 2>&1; then
        print_warn "jq not found - using fallback method for node group check"
        # Fallback: just check if node group exists and has any capacity
        local nodegroup_status=$(eksctl get nodegroup --cluster $CLUSTER_NAME --region $AWS_REGION --name oats-nodes --output table 2>/dev/null | grep -E "DESIRED CAPACITY" | awk '{print $3}')
        if [ "$nodegroup_status" = "0" ]; then
            return 1  # Node group has 0 capacity
        fi
        return 0  # Assume it has capacity
    fi
    
    # Get node group info
    local nodegroup_info=$(eksctl get nodegroup --cluster $CLUSTER_NAME --region $AWS_REGION --name oats-nodes --output json 2>/dev/null)
    
    if [ -z "$nodegroup_info" ]; then
        return 1  # Node group doesn't exist
    fi
    
    # Check if desired capacity is greater than 0
    local desired_capacity=$(echo "$nodegroup_info" | jq -r '.[0].DesiredCapacity // 0')
    local max_size=$(echo "$nodegroup_info" | jq -r '.[0].MaxSize // 0')
    local min_size=$(echo "$nodegroup_info" | jq -r '.[0].MinSize // 0')
    
    # If max size is 0, node group is effectively disabled
    if [ "$max_size" -eq 0 ] || [ "$desired_capacity" -eq 0 ]; then
        return 1  # Node group has no capacity
    fi
    
    return 0  # Node group has capacity
}

# Function to check if images are built locally
check_local_images() {
    local backend_exists=false
    local ui_exists=false
    
    # Check for images with the registry prefix
    if docker image inspect $REGISTRY/oats-backend-api:latest >/dev/null 2>&1; then
        backend_exists=true
    fi
    
    if docker image inspect $REGISTRY/oats-ui:latest >/dev/null 2>&1; then
        ui_exists=true
    fi
    
    if $backend_exists && $ui_exists; then
        return 0  # Both images exist
    else
        return 1  # At least one missing
    fi
}

# Function to check if images need to be rebuilt (optional - can be enhanced)
check_image_freshness() {
    # This is a simple check - in production you might want to compare
    # image timestamps with source code modification times
    local backend_age=""
    local ui_age=""
    
    if docker image inspect $REGISTRY/oats-backend-api:latest >/dev/null 2>&1; then
        backend_age=$(docker image inspect $REGISTRY/oats-backend-api:latest --format='{{.Created}}' 2>/dev/null || echo "")
    fi
    
    if docker image inspect $REGISTRY/oats-ui:latest >/dev/null 2>&1; then
        ui_age=$(docker image inspect $REGISTRY/oats-ui:latest --format='{{.Created}}' 2>/dev/null || echo "")
    fi
    
    # For now, just return that images exist - can be enhanced later
    if [ -n "$backend_age" ] && [ -n "$ui_age" ]; then
        return 0  # Images exist
    else
        return 1  # Images missing
    fi
}

# Function to check if pods are running
check_deployment_status() {
    if kubectl get pods -l app=oats-backend-api --no-headers 2>/dev/null | grep -q Running; then
        return 0  # Deployment exists and running
    else
        return 1  # Not deployed or not running
    fi
}

# Check what needs to be done
print_step "Checking current deployment status..."

NEED_ECR=false
NEED_EKS=false
NEED_SCALE_NODES=false
NEED_BUILD=false
NEED_DEPLOY=false

if ! check_ecr_repos; then
    NEED_ECR=true
    print_warn "ECR repositories missing"
else
    print_skip "ECR repositories already exist"
fi

if ! check_eks_cluster; then
    # Check if cluster exists but has no nodes
    if eksctl get cluster --name $CLUSTER_NAME --region $AWS_REGION >/dev/null 2>&1; then
        # Cluster exists but no nodes - check if node group needs scaling
        if ! check_nodegroup_capacity; then
            NEED_SCALE_NODES=true
            print_warn "EKS cluster exists but nodes are scaled down (0 capacity)"
        else
            NEED_EKS=true
            print_warn "EKS cluster exists but no nodes are ready"
        fi
    else
        NEED_EKS=true
        print_warn "EKS cluster missing"
    fi
else
    print_skip "EKS cluster already exists with ready nodes"
fi

if ! check_local_images; then
    NEED_BUILD=true
    print_warn "Local Docker images missing"
else
    print_skip "Local Docker images already built"
fi

if ! check_deployment_status; then
    NEED_DEPLOY=true
    print_warn "Kubernetes deployment missing or not running"
else
    print_skip "Kubernetes deployment already running"
fi

echo ""
print_info "Deployment plan:"
if $NEED_ECR; then echo "  ✓ Create ECR repositories"; else echo "  ⏭️  Skip ECR repositories"; fi
if $NEED_EKS; then echo "  ✓ Create EKS cluster (~15 min)"; else echo "  ⏭️  Skip EKS cluster"; fi
if $NEED_SCALE_NODES; then echo "  ✓ Scale up EKS nodes (2-3 min)"; else echo "  ⏭️  Skip node scaling"; fi
if $NEED_BUILD; then echo "  ✓ Build and push Docker images"; else echo "  ⏭️  Skip Docker build/push"; fi
if $NEED_DEPLOY; then echo "  ✓ Deploy to Kubernetes"; else echo "  ⏭️  Skip Kubernetes deployment"; fi

if ! $NEED_ECR && ! $NEED_EKS && ! $NEED_SCALE_NODES && ! $NEED_BUILD && ! $NEED_DEPLOY; then
    print_info "Everything is already deployed! 🎉"
    echo ""
    echo "Current status:"
    kubectl get pods
    echo ""
    
    # Show access URLs even when everything is deployed
    get_service_urls
    
    exit 0
fi

echo ""
read -p "Continue with missing components? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Deployment cancelled"
    exit 0
fi

# Ask about force rebuild if images exist
if ! $NEED_BUILD && check_local_images; then
    echo ""
    read -p "Force rebuild images even though they exist? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        NEED_BUILD=true
        print_warn "Force rebuild enabled"
    fi
fi

# Execute required steps
echo ""
print_step "Executing deployment steps..."

# Step 1: ECR repositories
if $NEED_ECR; then
    print_step "Creating ECR repositories..."
    ./scripts/deploy-aws.sh <<< "1"
fi

# Step 2: EKS cluster
if $NEED_EKS; then
    print_step "Creating EKS cluster..."
    ./scripts/deploy-aws.sh <<< "2"
fi

# Step 2.5: Scale up nodes (if cluster exists but nodes are scaled down)
if $NEED_SCALE_NODES; then
    print_step "Scaling up EKS nodes..."
    print_info "Setting node group capacity to 2 nodes (min: 1, max: 4)..."
    eksctl scale nodegroup --cluster $CLUSTER_NAME --name oats-nodes --nodes 2 --nodes-min 1 --nodes-max 4 --region $AWS_REGION
    
    print_info "Waiting for nodes to be ready (this may take 2-3 minutes)..."
    attempts=0
    max_attempts=20  # 2 minutes with 6-second intervals
    
    while [ $attempts -lt $max_attempts ]; do
        if kubectl get nodes --no-headers 2>/dev/null | grep -q Ready; then
            print_info "Nodes are ready! 🎉"
            break
        fi
        
        echo -n "."
        sleep 6
        attempts=$((attempts + 1))
    done
    
    if [ $attempts -eq $max_attempts ]; then
        print_warn "Nodes are taking longer than expected to start. Continuing anyway..."
    fi
    
    echo ""
fi

# Step 3: Build and push images
if $NEED_BUILD; then
    print_step "Building and pushing images..."
    ./scripts/deploy-aws.sh <<< "3"
fi

# Step 4: Deploy to Kubernetes
if $NEED_DEPLOY; then
    print_step "Deploying to Kubernetes..."
    ./scripts/deploy-aws.sh <<< "4"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "  Deployment Complete!"
echo "==========================================${NC}"
echo ""

# Show access URLs
get_service_urls

echo -e "${GREEN}📊 Management Commands:${NC}"
echo "  View pods:           kubectl get pods"
echo "  View services:       kubectl get services"
echo "  View logs (backend): kubectl logs -l app=oats-backend-api -f"
echo "  View logs (UI):      kubectl logs -l app=oats-ui -f"
echo ""
echo -e "${GREEN}💰 Cost Management:${NC}"
echo "  Scale down (save $): eksctl scale nodegroup --cluster=$CLUSTER_NAME --name=oats-nodes --nodes=0 --region=$AWS_REGION"
echo "  Scale back up:       eksctl scale nodegroup --cluster=$CLUSTER_NAME --name=oats-nodes --nodes=2 --region=$AWS_REGION"
echo ""
