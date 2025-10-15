# AWS EKS Cost Saving Guide

Quick reference for managing AWS costs when not actively using the OATS cluster.

## Cost Control Script

Use the interactive cost control script:
```bash
./scripts/cost-control.sh
```

## Cost-Saving Options

### 1. Scale Deployments to 0 (Quick Pause)
**Saves:** ~5-10% (reduces CPU/memory usage)
**Cost:** ~$66-139/month (nodes still running)
**Best for:** Short breaks (minutes to hours)
**Resume time:** Instant

```bash
./scripts/cost-control.sh  # Choose option 1
```

### 2. Pause Cluster (Stop All Nodes) ⭐ RECOMMENDED
**Saves:** ~90%
**Cost:** ~$73/month (only control plane)
**Best for:** Days to weeks of inactivity
**Resume time:** 2-3 minutes

```bash
# Pause
./scripts/cost-control.sh  # Choose option 3

# Resume
./scripts/cost-control.sh  # Choose option 4, then option 2
```

### 3. Full Teardown (Delete Cluster)
**Saves:** 100%
**Cost:** $0
**Best for:** Extended breaks (weeks to months)
**Resume time:** 15-20 minutes (full redeployment)

```bash
./scripts/cost-control.sh  # Choose option 5
```

## Cost Breakdown

| Resource | Cost (Approximate) |
|----------|-------------------|
| EKS Control Plane | ~$73/month |
| t3.medium node | ~$30/month per node |
| EBS volume (30GB) | ~$3/month per volume |

**Current Setup (2 nodes):**
- Running: ~$139/month
- Paused: ~$73/month (47% savings)
- Deleted: $0/month (100% savings)

## Typical Workflow

### Taking a Break
```bash
./scripts/cost-control.sh
# Choose option 3 (Pause cluster)
# Confirm with 'y'
# Wait ~1-2 minutes for nodes to terminate
```

### Resuming Work
```bash
./scripts/cost-control.sh
# Choose option 4 (Resume cluster)
# Enter number of nodes (default: 2)
# Wait ~2-3 minutes for nodes to start

# Then restore deployments
./scripts/cost-control.sh
# Choose option 2 (Restore deployments)
```

## Additional Options

### Check Current Status
```bash
./scripts/cost-control.sh  # Choose option 6
```

Shows:
- Node groups
- Running nodes
- Deployments and replicas
- Pod status

### Estimate Costs
```bash
./scripts/cost-control.sh  # Choose option 7
```

## Manual Commands

### Scale using AWS CLI directly
```bash
# Pause (scale to 0)
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name eksctl-oats-dev-nodegroup-oats-nodes-NodeGroup-vFyog92WC4vT \
  --min-size 0 --max-size 0 --desired-capacity 0 \
  --region us-west-2

# Resume (scale to 2)
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name eksctl-oats-dev-nodegroup-oats-nodes-NodeGroup-vFyog92WC4vT \
  --min-size 1 --max-size 4 --desired-capacity 2 \
  --region us-west-2
```

### Using eksctl
```bash
# Pause
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes \
  --nodes=0 --nodes-min=0 --region=us-west-2

# Resume
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes \
  --nodes=2 --nodes-min=1 --nodes-max=4 --region=us-west-2
```

## Important Notes

1. **Control Plane Always Runs:** The EKS control plane costs ~$73/month even when nodes are stopped. Only full deletion eliminates all costs.

2. **Data Persistence:** Pausing the cluster preserves all configurations, deployments, and persistent volumes. Only the compute nodes are stopped.

3. **Startup Time:** Nodes take 2-3 minutes to start. Plan accordingly if you need immediate access.

4. **Full Teardown:** If you delete the cluster entirely, you'll need to run the full deployment process again:
   ```bash
   ./scripts/deploy-aws.sh  # Choose option 5 (Full deployment)
   ```

5. **Cost Monitoring:** Always verify actual costs in [AWS Cost Explorer](https://console.aws.amazon.com/cost-management/home#/cost-explorer).

## Automation Ideas

### Nightly Shutdown Script
```bash
# Add to crontab for automatic nightly shutdown (8 PM PST)
0 20 * * * /Users/sgupta/oats/scripts/cost-control.sh <<< "3" <<< "y"
```

### Morning Startup Script
```bash
# Add to crontab for automatic morning startup (8 AM PST)
0 8 * * 1-5 /Users/sgupta/oats/scripts/cost-control.sh <<< "4" <<< "2"
```

## Troubleshooting

### Script can't find node groups
If the script fails to find node groups:
```bash
# Check if eksctl can see them
eksctl get nodegroup --cluster oats-dev --region us-west-2

# Check Auto Scaling Groups
aws autoscaling describe-auto-scaling-groups --region us-west-2 \
  --query "AutoScalingGroups[?contains(AutoScalingGroupName, 'oats-dev')]"
```

### Nodes not starting after resume
```bash
# Check ASG desired capacity
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-name eksctl-oats-dev-nodegroup-oats-nodes-NodeGroup-vFyog92WC4vT \
  --region us-west-2 \
  --query 'AutoScalingGroups[0].[MinSize,MaxSize,DesiredCapacity]'

# Check EC2 instances
kubectl get nodes -o wide
```

### Pods stuck in Pending state
```bash
# Check if nodes are ready first
kubectl get nodes

# If nodes are ready, check pod status
kubectl describe pod <pod-name>

# Restart deployments if needed
kubectl rollout restart deployment --all
```
