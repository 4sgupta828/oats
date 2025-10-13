#!/bin/bash
# One-command deployment for OATS on AWS EKS
# Usage: ./DEPLOY.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================="
echo "  OATS AWS Deployment"
echo "  Account: 911167909198"
echo "==========================================${NC}"
echo ""

# Load AWS configuration
source .env.aws

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo -e "${YELLOW}AWS CLI not configured. Running 'aws configure'...${NC}"
    aws configure
fi

# Check if Anthropic API key is set (we use Claude by default)
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${YELLOW}ANTHROPIC_API_KEY not set${NC}"
    read -sp "Enter your Anthropic API key: " ANTHROPIC_API_KEY
    echo ""
    export ANTHROPIC_API_KEY
fi

echo ""
echo "Ready to deploy with:"
echo "  Registry: $REGISTRY"
echo "  Region: $AWS_REGION"
echo "  Cluster: $CLUSTER_NAME"
echo ""
echo "This will:"
echo "  1. Create ECR repositories"
echo "  2. Create EKS cluster (2 nodes, ~15 min)"
echo "  3. Build and push Docker images"
echo "  4. Deploy OATS to EKS"
echo ""
read -p "Continue? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Run the interactive script with automatic full deployment
./scripts/deploy-aws.sh <<EOF
5
EOF

echo ""
echo -e "${GREEN}=========================================="
echo "  Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Enable LoadBalancer access:"
echo "     kubectl patch service oats-backend-api-service -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'"
echo ""
echo "  2. Or use port-forwarding:"
echo "     kubectl port-forward service/oats-backend-api-service 8000:8000"
echo ""
echo "  3. Test the agent:"
echo "     curl -X POST http://localhost:8000/api/v1/jobs \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"goal\": \"Check health of all pods\", \"max_turns\": 10}'"
echo ""
echo "View logs:"
echo "  kubectl logs -l app=oats-backend-api -f"
echo ""
echo "Stop cluster when done (save costs):"
echo "  eksctl scale nodegroup --cluster=$CLUSTER_NAME --name=oats-nodes --nodes=0"
echo ""
