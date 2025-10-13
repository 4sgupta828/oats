#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
CLUSTER_NAME="${CLUSTER_NAME:-oats-dev}"
AWS_REGION="${AWS_REGION:-us-west-2}"
NODE_COUNT="${NODE_COUNT:-2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
print_info "Checking prerequisites..."

if ! command_exists aws; then
    print_error "aws CLI not found. Install from: https://aws.amazon.com/cli/"
    exit 1
fi

if ! command_exists eksctl; then
    print_error "eksctl not found. Install from: https://eksctl.io/"
    exit 1
fi

if ! command_exists kubectl; then
    print_error "kubectl not found. Install from: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

if ! command_exists docker; then
    print_error "docker not found. Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Get AWS account ID
print_info "Getting AWS account information..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    print_error "Failed to get AWS account ID. Check your AWS credentials."
    exit 1
fi

print_info "AWS Account ID: $AWS_ACCOUNT_ID"
print_info "Region: $AWS_REGION"

# Set registry
export REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Main menu
echo ""
echo "=========================================="
echo "  OATS AWS EKS Deployment Script"
echo "=========================================="
echo ""
echo "What would you like to do?"
echo "1) Create ECR repositories"
echo "2) Create EKS cluster"
echo "3) Build and push images"
echo "4) Deploy OATS to EKS"
echo "5) Full deployment (steps 1-4)"
echo "6) Check deployment status"
echo "7) Get access URLs"
echo "8) Teardown (delete cluster)"
echo "9) Exit"
echo ""
read -p "Enter choice [1-9]: " choice

case $choice in
    1)
        print_info "Creating ECR repositories..."

        # Check if repositories already exist
        if aws ecr describe-repositories --repository-names oats-backend-api --region $AWS_REGION >/dev/null 2>&1; then
            print_warn "Repository oats-backend-api already exists"
        else
            aws ecr create-repository --repository-name oats-backend-api --region $AWS_REGION
            print_info "Created repository: oats-backend-api"
        fi

        if aws ecr describe-repositories --repository-names oats-ui --region $AWS_REGION >/dev/null 2>&1; then
            print_warn "Repository oats-ui already exists"
        else
            aws ecr create-repository --repository-name oats-ui --region $AWS_REGION
            print_info "Created repository: oats-ui"
        fi

        print_info "ECR repositories ready at: ${REGISTRY}"
        ;;

    2)
        print_info "Creating EKS cluster: $CLUSTER_NAME"
        print_warn "This will take approximately 15-20 minutes..."

        # Check if cluster already exists
        if eksctl get cluster --name $CLUSTER_NAME --region $AWS_REGION >/dev/null 2>&1; then
            print_warn "Cluster $CLUSTER_NAME already exists"
            read -p "Do you want to continue anyway? (y/n): " continue
            if [ "$continue" != "y" ]; then
                exit 0
            fi
        fi

        # Create cluster config
        cat > /tmp/oats-cluster.yaml <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: $CLUSTER_NAME
  region: $AWS_REGION

nodeGroups:
  - name: oats-nodes
    instanceType: $INSTANCE_TYPE
    desiredCapacity: $NODE_COUNT
    minSize: 1
    maxSize: 4
    volumeSize: 30
    ssh:
      allow: false
    iam:
      withAddonPolicies:
        imageBuilder: true
        autoScaler: true
        cloudWatch: true

addons:
  - name: vpc-cni
  - name: coredns
  - name: kube-proxy
EOF

        eksctl create cluster -f /tmp/oats-cluster.yaml

        print_info "Cluster created successfully!"
        print_info "Updating kubeconfig..."
        aws eks update-kubeconfig --name $CLUSTER_NAME --region $AWS_REGION

        print_info "Verifying nodes..."
        kubectl get nodes
        ;;

    3)
        print_info "Building and pushing images..."

        # Docker login to ECR
        print_info "Logging in to ECR..."
        aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REGISTRY

        # Build images
        print_info "Building images with REGISTRY=${REGISTRY}..."
        cd "$(dirname "$0")/.." # Go to project root
        REGISTRY=$REGISTRY make build

        # Push images
        print_info "Pushing images to ECR..."
        REGISTRY=$REGISTRY make push

        print_info "Images pushed successfully!"
        ;;

    4)
        print_info "Deploying OATS to EKS..."

        # Check if secrets exist
        if ! kubectl get secret oats-api-keys >/dev/null 2>&1; then
            print_warn "Secret 'oats-api-keys' not found. Creating from environment variables..."

            # Check for Anthropic API key (primary, since we use Claude)
            if [ -z "$ANTHROPIC_API_KEY" ]; then
                print_error "ANTHROPIC_API_KEY environment variable not set"
                read -sp "Enter Anthropic API key: " ANTHROPIC_API_KEY
                echo ""
            fi

            # OpenAI key is optional
            OPENAI_KEY="${OPENAI_API_KEY:-dummy}"

            kubectl create secret generic oats-api-keys \
                --from-literal=anthropic-api-key="$ANTHROPIC_API_KEY" \
                --from-literal=openai-api-key="$OPENAI_KEY"

            print_info "Secret created (using Claude/Anthropic)"
        else
            print_info "Secret 'oats-api-keys' already exists"
        fi

        # Deploy to Kubernetes
        cd "$(dirname "$0")/.." # Go to project root
        print_info "Deploying with REGISTRY=${REGISTRY}..."
        REGISTRY=$REGISTRY make deploy-cloud

        print_info "Deployment complete!"
        print_info "Waiting for pods to be ready..."
        kubectl wait --for=condition=ready pod -l app=oats-backend-api --timeout=120s || true

        kubectl get pods
        ;;

    5)
        print_info "Running full deployment..."

        # Step 1: ECR
        print_info "Step 1/4: Creating ECR repositories..."
        bash "$0" <<< "1"

        # Step 2: EKS
        print_info "Step 2/4: Creating EKS cluster..."
        bash "$0" <<< "2"

        # Step 3: Build & Push
        print_info "Step 3/4: Building and pushing images..."
        bash "$0" <<< "3"

        # Step 4: Deploy
        print_info "Step 4/4: Deploying OATS..."
        bash "$0" <<< "4"

        print_info "Full deployment complete!"
        bash "$0" <<< "7" # Show access URLs
        ;;

    6)
        print_info "Checking deployment status..."

        echo ""
        echo "Pods:"
        kubectl get pods

        echo ""
        echo "Services:"
        kubectl get services

        echo ""
        echo "Deployments:"
        kubectl get deployments

        echo ""
        echo "Recent events:"
        kubectl get events --sort-by='.lastTimestamp' | tail -10
        ;;

    7)
        print_info "Getting access URLs..."

        echo ""
        echo "=========================================="
        echo "  Access Information"
        echo "=========================================="
        echo ""

        # Check if LoadBalancer is configured
        BACKEND_LB=$(kubectl get service oats-backend-api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
        UI_LB=$(kubectl get service oats-ui-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

        if [ -n "$BACKEND_LB" ]; then
            echo "Backend API (LoadBalancer): http://${BACKEND_LB}:8000/docs"
        else
            echo "Backend API: LoadBalancer not configured"
            echo "  To enable: kubectl patch service oats-backend-api-service -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'"
            echo "  Or port-forward: kubectl port-forward service/oats-backend-api-service 8000:8000"
        fi

        if [ -n "$UI_LB" ]; then
            echo "UI (LoadBalancer): http://${UI_LB}:8080"
        else
            echo "UI: LoadBalancer not configured"
            echo "  To enable: kubectl patch service oats-ui-service -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'"
            echo "  Or port-forward: kubectl port-forward service/oats-ui-service 8080:8080"
        fi

        echo ""
        echo "To view logs:"
        echo "  Backend: kubectl logs -l app=oats-backend-api -f"
        echo "  UI: kubectl logs -l app=oats-ui -f"
        echo ""
        ;;

    8)
        print_warn "This will DELETE the EKS cluster and all resources!"
        read -p "Are you sure? Type 'yes' to confirm: " confirm

        if [ "$confirm" != "yes" ]; then
            print_info "Teardown cancelled"
            exit 0
        fi

        print_info "Deleting Kubernetes resources..."
        kubectl delete -f infra/base/ --ignore-not-found=true || true

        print_info "Deleting EKS cluster: $CLUSTER_NAME"
        eksctl delete cluster --name $CLUSTER_NAME --region $AWS_REGION --wait

        print_info "Cluster deleted successfully!"

        read -p "Delete ECR repositories too? (y/n): " delete_ecr
        if [ "$delete_ecr" = "y" ]; then
            print_info "Deleting ECR repositories..."
            aws ecr delete-repository --repository-name oats-backend-api --region $AWS_REGION --force || true
            aws ecr delete-repository --repository-name oats-ui --region $AWS_REGION --force || true
            print_info "ECR repositories deleted"
        fi
        ;;

    9)
        print_info "Exiting..."
        exit 0
        ;;

    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac

echo ""
print_info "Done!"
