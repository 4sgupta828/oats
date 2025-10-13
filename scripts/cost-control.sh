#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
CLUSTER_NAME="${CLUSTER_NAME:-oats-dev}"
AWS_REGION="${AWS_REGION:-us-west-2}"

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=========================================="
    echo -e "  $1"
    echo -e "==========================================${NC}"
}

# Function to scale deployments
scale_deployments() {
    local replicas=$1
    print_info "Scaling all deployments to $replicas replicas..."
    kubectl scale deployment --all --replicas=$replicas -n default
    print_info "Deployments scaled!"
}

# Function to pause cluster (scale nodes to 0)
pause_cluster() {
    print_warn "This will scale down all node groups to 0 nodes"
    print_warn "The control plane will continue running (minimal cost)"
    read -p "Continue? (y/n): " confirm

    if [ "$confirm" != "y" ]; then
        print_info "Operation cancelled"
        return
    fi

    print_info "Getting Auto Scaling Groups for cluster..."

    # Find ASGs tagged with this cluster (try multiple tag formats)
    asg_names=$(aws autoscaling describe-auto-scaling-groups \
        --region $AWS_REGION \
        --query "AutoScalingGroups[?Tags[?Key=='alpha.eksctl.io/cluster-name' && Value=='$CLUSTER_NAME']].AutoScalingGroupName" \
        --output text)

    # Fallback to other tag formats if not found
    if [ -z "$asg_names" ]; then
        asg_names=$(aws autoscaling describe-auto-scaling-groups \
            --region $AWS_REGION \
            --query "AutoScalingGroups[?Tags[?Key=='eks:cluster-name' && Value=='$CLUSTER_NAME']].AutoScalingGroupName" \
            --output text)
    fi

    if [ -z "$asg_names" ]; then
        print_error "No Auto Scaling Groups found for cluster $CLUSTER_NAME"
        print_info "Trying with eksctl..."

        # Try with eksctl
        nodegroups=$(eksctl get nodegroup --cluster $CLUSTER_NAME --region $AWS_REGION -o json 2>/dev/null | jq -r '.[].Name' 2>/dev/null)

        if [ -z "$nodegroups" ]; then
            print_error "Could not find node groups"
            return 1
        fi

        for ng in $nodegroups; do
            print_info "Scaling nodegroup $ng to 0 via eksctl..."
            eksctl scale nodegroup --cluster=$CLUSTER_NAME --name=$ng --nodes=0 --nodes-min=0 --region=$AWS_REGION
        done
    else
        # Scale ASGs directly
        for asg in $asg_names; do
            print_info "Scaling ASG $asg to 0..."
            aws autoscaling update-auto-scaling-group \
                --auto-scaling-group-name $asg \
                --min-size 0 \
                --max-size 0 \
                --desired-capacity 0 \
                --region $AWS_REGION
            print_info "✓ $asg scaled to 0"
        done
    fi

    print_info "All node groups scaled to 0"
    print_info "Nodes will terminate in 1-2 minutes"
    print_info "To resume, run this script and choose 'Resume cluster'"
}

# Function to resume cluster
resume_cluster() {
    read -p "How many nodes do you want? (default 2): " node_count
    node_count=${node_count:-2}

    print_info "Getting Auto Scaling Groups for cluster..."

    # Find ASGs tagged with this cluster (try multiple tag formats)
    asg_names=$(aws autoscaling describe-auto-scaling-groups \
        --region $AWS_REGION \
        --query "AutoScalingGroups[?Tags[?Key=='alpha.eksctl.io/cluster-name' && Value=='$CLUSTER_NAME']].AutoScalingGroupName" \
        --output text)

    # Fallback to other tag formats if not found
    if [ -z "$asg_names" ]; then
        asg_names=$(aws autoscaling describe-auto-scaling-groups \
            --region $AWS_REGION \
            --query "AutoScalingGroups[?Tags[?Key=='eks:cluster-name' && Value=='$CLUSTER_NAME']].AutoScalingGroupName" \
            --output text)
    fi

    if [ -z "$asg_names" ]; then
        print_error "No Auto Scaling Groups found for cluster $CLUSTER_NAME"
        print_info "Trying with eksctl..."

        # Try with eksctl
        nodegroups=$(eksctl get nodegroup --cluster $CLUSTER_NAME --region $AWS_REGION -o json 2>/dev/null | jq -r '.[].Name' 2>/dev/null)

        if [ -z "$nodegroups" ]; then
            print_error "Could not find node groups"
            return 1
        fi

        for ng in $nodegroups; do
            print_info "Scaling nodegroup $ng to $node_count nodes via eksctl..."
            eksctl scale nodegroup --cluster=$CLUSTER_NAME --name=$ng --nodes=$node_count --nodes-min=1 --nodes-max=4 --region=$AWS_REGION
        done
    else
        # Scale ASGs directly
        for asg in $asg_names; do
            print_info "Scaling ASG $asg to $node_count nodes..."
            aws autoscaling update-auto-scaling-group \
                --auto-scaling-group-name $asg \
                --min-size 1 \
                --max-size 4 \
                --desired-capacity $node_count \
                --region $AWS_REGION
            print_info "✓ $asg scaling to $node_count nodes"
        done
    fi

    print_info "Node groups scaling up to $node_count nodes..."
    print_info "Waiting for nodes to be ready (this may take 2-3 minutes)..."

    # Wait for nodes
    sleep 30
    for i in {1..20}; do
        ready_nodes=$(kubectl get nodes --no-headers 2>/dev/null | grep -c "Ready" || echo "0")
        if [ "$ready_nodes" -ge "$node_count" ]; then
            print_info "✓ All nodes are ready!"
            break
        fi
        echo -n "."
        sleep 10
    done
    echo ""

    kubectl get nodes
}

# Function to show current status
show_status() {
    print_header "Current Status"

    echo ""
    print_info "Cluster: $CLUSTER_NAME (region: $AWS_REGION)"

    echo ""
    echo "Node Groups:"
    aws eks list-nodegroups --cluster-name $CLUSTER_NAME --region $AWS_REGION --output table 2>/dev/null || echo "No node groups found"

    echo ""
    echo "Nodes:"
    kubectl get nodes 2>/dev/null || echo "No nodes available"

    echo ""
    echo "Deployments:"
    kubectl get deployments -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas,READY:.status.readyReplicas 2>/dev/null || echo "No deployments found"

    echo ""
    echo "Pods:"
    kubectl get pods 2>/dev/null || echo "No pods available"
}

# Function to estimate costs
estimate_costs() {
    print_header "Cost Estimates (approximate)"
    echo ""
    echo "EKS Control Plane: ~\$73/month (runs even when nodes are stopped)"
    echo "t3.medium nodes: ~\$30/month per node"
    echo "EBS volumes: ~\$3/month per 30GB volume"
    echo ""
    echo "Cost Saving Options:"
    echo "1. Scale deployments to 0: Saves 0% (nodes still running)"
    echo "2. Pause cluster (0 nodes): Saves ~90% (only control plane)"
    echo "3. Delete cluster: Saves 100% (need to recreate later)"
    echo ""

    # Try to get actual node count
    node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | xargs)
    if [ "$node_count" -gt 0 ]; then
        monthly_estimate=$((73 + node_count * 30 + node_count * 3))
        echo "Current estimated cost: ~\$${monthly_estimate}/month (${node_count} nodes)"
    fi

    echo ""
    echo "For exact costs, check AWS Cost Explorer"
}

# Main menu
print_header "OATS Cost Control"
echo ""
echo "Cluster: $CLUSTER_NAME"
echo "Region: $AWS_REGION"
echo ""
echo "What would you like to do?"
echo ""
echo "Cost-Saving Actions:"
echo "  1) Scale deployments to 0 (quick pause, nodes still running)"
echo "  2) Restore deployments (scale back to 1 replica)"
echo "  3) Pause cluster (stop all nodes, keeps cluster)"
echo "  4) Resume cluster (restart nodes)"
echo "  5) Full teardown (delete entire cluster)"
echo ""
echo "Information:"
echo "  6) Show current status"
echo "  7) Estimate costs"
echo "  8) Exit"
echo ""
read -p "Enter choice [1-8]: " choice

case $choice in
    1)
        print_info "Scaling deployments to 0..."
        scale_deployments 0
        print_info "Deployments scaled down. Nodes are still running."
        print_info "To save more, choose 'Pause cluster' (option 3)"
        ;;

    2)
        print_info "Restoring deployments..."
        scale_deployments 1
        print_info "Waiting for pods to be ready..."
        kubectl wait --for=condition=ready pod -l app=oats-backend-api --timeout=120s || true
        kubectl get pods
        ;;

    3)
        pause_cluster
        ;;

    4)
        resume_cluster
        print_info "After nodes are ready, restore your deployments with option 2"
        ;;

    5)
        print_warn "This will DELETE the entire cluster!"
        print_warn "You'll need to run deploy-aws.sh to recreate it"
        echo ""
        read -p "Are you absolutely sure? Type 'DELETE' to confirm: " confirm

        if [ "$confirm" != "DELETE" ]; then
            print_info "Teardown cancelled"
            exit 0
        fi

        # Use the existing deploy script's teardown
        cd "$(dirname "$0")"
        bash deploy-aws.sh <<< "8"
        ;;

    6)
        show_status
        ;;

    7)
        estimate_costs
        ;;

    8)
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
