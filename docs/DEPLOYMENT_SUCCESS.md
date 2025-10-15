# 🎉 OATS Successfully Deployed to AWS EKS!

## ✅ Deployment Complete

Your OATS Infrastructure Co-Pilot is now running on AWS with Claude (Anthropic) as the LLM provider.

## 🌐 Access Your Application

### Backend API (FastAPI + Socket.IO)
```
http://a19ebab9dc68f476bb249e3a2e3af44d-1020250872.us-west-2.elb.amazonaws.com:8000/docs
```

### UI (React Interface)
```
http://a4a843fad3124415f86e7b8cefb14401-219797074.us-west-2.elb.amazonaws.com:8080
```

## 🧪 Test the Agent

Open the UI URL in your browser and try these test goals:

### Simple Test
```
Check the health of all pods in the default namespace
```

### Self-Diagnosis Test
```
Diagnose the oats-backend-api deployment and check if it's healthy
```

### Advanced Test
```
Investigate why any pods might be consuming high resources
```

## 📊 What's Running

### Cluster Information
- **AWS Account:** 911167909198
- **Region:** us-west-2
- **Cluster:** oats-dev
- **Nodes:** 2x t3.medium

### Deployed Components
- ✅ **Backend API** (oats-backend-api)
  - FastAPI + Socket.IO server
  - Embedded OATS agent
  - Claude 3.5 Sonnet LLM
  - 11 SRE tools available

- ✅ **UI** (oats-ui)
  - React single-page application
  - Real-time WebSocket connection
  - Simplified architecture (direct backend connection)

### Services
```bash
kubectl get services
```

| Service | Type | External URL |
|---------|------|--------------|
| oats-backend-api | LoadBalancer | Port 8000 |
| oats-ui-service | LoadBalancer | Port 8080 |

## 🔧 What We Fixed

### Issue #1: Platform Architecture Mismatch
**Problem:** Images built on Apple Silicon (ARM64) couldn't run on AWS EC2 (AMD64)

**Solution:** Rebuilt images with `--platform linux/amd64`
```bash
docker buildx build --platform linux/amd64 ...
```

### Issue #2: UI Not Connecting to Backend
**Problem:** UI was hardcoded to `localhost:8000`

**Solution:** Updated to use backend LoadBalancer URL directly
- Removed nginx proxy complexity
- Direct Socket.IO connection
- CORS already enabled on backend

## 🚀 How It Works

1. **User visits UI** → LoadBalancer serves React app
2. **UI connects** → Direct WebSocket to backend LoadBalancer
3. **User enters goal** → Sent via Socket.IO
4. **Backend spawns agent** → Uses Claude 3.5 Sonnet
5. **Agent investigates** → Queries Kubernetes API, runs tools
6. **Real-time updates** → Streamed back to UI via WebSocket

## 💡 Agent Capabilities

Your agent can now:
- ✅ **Query Kubernetes API** - List pods, services, deployments
- ✅ **Check pod health** - Resource usage, status, logs
- ✅ **Diagnose issues** - Systematic RCA using 7-phase framework
- ✅ **Self-operate** - Investigate its own cluster
- ✅ **Execute tools** - 11 SRE tools available

## 📋 Common Commands

### View Logs
```bash
# Backend logs
kubectl logs -l app=oats-backend-api -f

# UI logs
kubectl logs -l app=oats-ui -f
```

### Check Status
```bash
# All pods
kubectl get pods

# All services
kubectl get services

# Deployments
kubectl get deployments
```

### Update Application
```bash
# Rebuild and push images
cd /Users/sgupta/oats
source .env.aws
docker buildx build --platform linux/amd64 -t $REGISTRY/oats-backend-api:latest -f ./services/backend-api/Dockerfile . --load
docker push $REGISTRY/oats-backend-api:latest

# Restart pods
kubectl rollout restart deployment/oats-backend-api
```

### Restart Services
```bash
# Restart backend
kubectl rollout restart deployment/oats-backend-api

# Restart UI
kubectl rollout restart deployment/oats-ui
```

## 💰 Cost Management

### Current Monthly Costs
- EKS Control Plane: $73/month (fixed)
- 2x t3.medium nodes: $60/month
- **Total: ~$133/month** (running 24/7)

### Save Money

**Option 1: Scale down when not using**
```bash
eksctl scale nodegroup --cluster=oats-dev --name=oats-nodes --nodes=0
# Saves: $60/month, costs: $73/month
```

**Option 2: Delete completely**
```bash
eksctl delete cluster --name=oats-dev --region=us-west-2
# Saves: $133/month, costs: $0/month
```

## 🔐 Security Notes

- ✅ RBAC configured with least privilege
- ✅ ServiceAccount: `oats-backend`
- ✅ Secrets stored in Kubernetes
- ✅ ANTHROPIC_API_KEY set via secrets
- ✅ No credentials in code

## 🐛 Troubleshooting

### UI shows "Disconnected"
**Check:**
1. Backend pod is running: `kubectl get pods`
2. Backend logs: `kubectl logs -l app=oats-backend-api`
3. Service is accessible: `kubectl get services`

**Fix:** Refresh the browser page

### Agent not responding
**Check backend logs:**
```bash
kubectl logs -l app=oats-backend-api -f
```

### "ImagePullBackOff" errors
**Rebuild for AMD64:**
```bash
docker buildx build --platform linux/amd64 ...
```

## 📚 Documentation

- **Main README:** `/Users/sgupta/oats/README.md`
- **Cloud Setup:** `/Users/sgupta/oats/docs/CLOUD_QUICK_START.md`
- **AWS Guide:** `/Users/sgupta/oats/docs/AWS_DEPLOYMENT.md`
- **Claude Setup:** `/Users/sgupta/oats/CLAUDE_SETUP.md`

## 🎯 Next Steps

1. **Test the agent** - Try the sample goals above
2. **Monitor costs** - Set up AWS billing alerts
3. **Add custom tools** - Extend for your infrastructure
4. **Set up monitoring** - CloudWatch, Prometheus, Grafana
5. **Create investigations** - Use for real incidents

## 🎊 Success Checklist

- ✅ EKS cluster created (2 nodes)
- ✅ ECR repositories created
- ✅ Images built for AMD64
- ✅ Images pushed to ECR
- ✅ Backend deployed and running
- ✅ UI deployed and running
- ✅ LoadBalancers provisioned
- ✅ UI connects to backend
- ✅ Claude API key configured
- ✅ Agent initialized with 11 tools
- ✅ RBAC permissions granted
- ✅ Ready for investigations!

---

**Your OATS Infrastructure Co-Pilot is live!** 🚀

Open the UI and start diagnosing:
```
http://a4a843fad3124415f86e7b8cefb14401-219797074.us-west-2.elb.amazonaws.com:8080
```
