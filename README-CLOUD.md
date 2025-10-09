# OATS Cloud: Multi-Phase Migration Guide

This document outlines the migration of OATS from a local CLI tool to a cloud-based service with UI.

## Project Structure

```
oats-copilot/
├── .gitignore
├── README.md                    # Original OATS documentation
├── README-CLOUD.md              # This file - Cloud migration guide
├── services/
│   ├── ui/                      # Phase 3: Frontend React/Vue application
│   │   ├── Dockerfile
│   │   └── README.md
│   ├── backend-api/             # Phase 1: Backend FastAPI server
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py          # FastAPI entrypoint, creates K8s Jobs
│   │   │   └── k8s_service.py   # Logic for interacting with Kubernetes API
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── agent/                   # Phase 1: Core OATS SRE Agent
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── main.py          # New entrypoint for container execution
│       │   ├── reactor/         # Will reference existing reactor logic
│       │   ├── core/            # Will reference existing core logic
│       │   └── tools/           # Will reference existing tools
│       ├── requirements.txt
│       └── Dockerfile
├── infra/                       # Phase 1: Kubernetes manifests
│   ├── base/
│   │   ├── backend-api-deployment.yaml
│   │   ├── rbac.yaml
│   │   └── secrets.yaml
│   └── README.md
├── core/                        # Existing: Core logic (unchanged for now)
├── reactor/                     # Existing: ReAct agent (unchanged for now)
├── tools/                       # Existing: SRE tools (unchanged for now)
├── executor/                    # Existing: Tool execution
├── orchestrator/                # Existing: Orchestration logic
└── registry/                    # Existing: Tool registry
```

## Migration Phases

### Phase 1: Containerization & Backend API (Current)
**Goal**: Deploy OATS as Kubernetes Jobs managed by a FastAPI backend

#### Status: ✅ Structure Created
- [x] Create services directory structure
- [x] Create backend API with K8s integration
- [x] Create agent container entrypoint
- [x] Create Kubernetes manifests
- [ ] **TODO**: Copy/symlink existing code to services/agent/agent/
- [ ] **TODO**: Test Docker builds
- [ ] **TODO**: Deploy to Kubernetes cluster
- [ ] **TODO**: Test end-to-end job execution

#### Components
1. **Backend API** (`services/backend-api/`)
   - FastAPI server exposing REST API
   - Creates Kubernetes Jobs for agent execution
   - Manages job lifecycle (create, monitor, delete)
   - Retrieves logs from agent pods

2. **Containerized Agent** (`services/agent/`)
   - Container wrapper around existing OATS agent
   - Reads goal from environment variables
   - Executes investigation and saves results
   - Runs as a Kubernetes Job

3. **Infrastructure** (`infra/`)
   - Kubernetes manifests for deployment
   - RBAC configuration
   - Secrets management

#### Testing Phase 1
```bash
# Build images
cd services/backend-api && docker build -t oats-backend-api:latest .
cd services/agent && docker build -t oats-agent:latest .

# Deploy to K8s
kubectl apply -f infra/base/

# Test API
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"goal": "Why is the API returning 504 errors?", "max_turns": 10}'
```

### Phase 2: Enhanced Observability
**Goal**: Add monitoring, logging, and alerting

#### TODO
- [ ] Add Prometheus metrics to backend API
- [ ] Create Grafana dashboards
- [ ] Set up log aggregation (Loki/Elasticsearch)
- [ ] Add distributed tracing
- [ ] Create alerting rules
- [ ] Add healthchecks and readiness probes

#### Components
1. **Metrics**
   - Job execution metrics (duration, success rate)
   - API metrics (request rate, latency)
   - Agent metrics (turn count, tool usage)

2. **Logging**
   - Structured logging for backend API
   - Agent execution logs
   - Audit logs for job operations

3. **Tracing**
   - End-to-end tracing from API → Job creation → Agent execution

### Phase 3: Frontend UI
**Goal**: Build user-friendly web interface

#### TODO
- [ ] Design UI/UX for job management
- [ ] Implement React/Vue frontend
- [ ] Add real-time log streaming (WebSocket)
- [ ] Create investigation visualization
- [ ] Build historical incident browser
- [ ] Add user authentication

#### Features
1. **Job Management**
   - Create new investigations
   - View active jobs
   - Cancel running jobs

2. **Real-time Monitoring**
   - Live log streaming
   - Progress tracking
   - Turn-by-turn investigation view

3. **Historical Analysis**
   - Search past incidents
   - Compare investigations
   - Export reports

### Phase 4: Multi-Cluster & High Availability
**Goal**: Production-grade deployment

#### TODO
- [ ] Multi-cluster support
- [ ] HA backend API (multiple replicas, load balancing)
- [ ] Job queuing system (Redis/RabbitMQ)
- [ ] Database for persistent storage (PostgreSQL)
- [ ] Auto-scaling for agent jobs
- [ ] Disaster recovery setup

## Migration Strategy

### Approach: Gradual Migration
The existing OATS codebase remains **unchanged** during Phase 1. The new cloud infrastructure wraps around it.

#### Step 1: Link Existing Code (Next Step)
```bash
# Option A: Symlinks (for development)
cd services/agent/agent/
ln -s ../../../reactor reactor
ln -s ../../../core core
ln -s ../../../tools tools

# Option B: Copy (for containerization)
cp -r reactor services/agent/agent/
cp -r core services/agent/agent/
cp -r tools services/agent/agent/
```

#### Step 2: Update Imports
Modify `services/agent/agent/main.py` to import existing modules:
```python
from reactor.agent_controller import AgentController
from registry.main import Registry
```

#### Step 3: Test Locally
```bash
# Set environment variables
export OATS_GOAL="Test investigation"
export OATS_MAX_TURNS=5
export OPENAI_API_KEY="your-key"

# Run containerized agent locally
python services/agent/agent/main.py
```

#### Step 4: Build & Deploy
```bash
# Build Docker images
docker build -t oats-agent:latest services/agent/

# Deploy to Kubernetes
kubectl apply -f infra/base/
```

## Key Design Decisions

### 1. Job-Based Architecture
- Each investigation runs as a separate Kubernetes Job
- Isolates agent execution from API server
- Enables horizontal scaling
- Provides automatic retry and failure handling

### 2. Stateless Backend API
- API server only manages jobs, doesn't execute investigations
- Results stored in persistent volume or object storage
- Enables HA deployment

### 3. Existing Code Preservation
- Phase 1 doesn't modify existing agent logic
- Container entrypoint is a thin wrapper
- Gradual refactoring in later phases

### 4. Security First
- RBAC with least privilege
- Secrets management (no hardcoded keys)
- Network policies for pod isolation
- Agent runs with read-only permissions

## Development Workflow

### Local Development
```bash
# Run backend API locally
cd services/backend-api
pip install -r requirements.txt
uvicorn app.main:app --reload

# Run agent locally (without K8s)
cd services/agent
python -m agent.main
```

### Testing
```bash
# Unit tests
pytest services/backend-api/tests/
pytest services/agent/tests/

# Integration tests
pytest tests/integration/

# E2E tests
pytest tests/e2e/
```

### CI/CD Pipeline
```yaml
# .github/workflows/deploy.yml
# TODO: Create GitHub Actions workflow
- Build Docker images
- Run tests
- Push to container registry
- Deploy to K8s (dev → staging → prod)
```

## Deployment Environments

### Development
- Local Kubernetes (minikube, kind, k3s)
- Single replica backend
- Short-lived agent jobs

### Staging
- Cloud Kubernetes (GKE, EKS, AKS)
- 2 backend replicas
- Full monitoring stack

### Production
- Multi-zone Kubernetes cluster
- 3+ backend replicas with auto-scaling
- HA database
- Full observability and alerting

## Next Steps

1. **Immediate** (Phase 1 completion):
   - Link/copy existing code to `services/agent/agent/`
   - Test Docker builds
   - Deploy to local Kubernetes cluster
   - Validate end-to-end flow

2. **Short-term** (Phase 2):
   - Add monitoring and observability
   - Set up CI/CD pipeline
   - Deploy to cloud environment

3. **Medium-term** (Phase 3):
   - Design and build frontend UI
   - Add authentication
   - Implement real-time features

4. **Long-term** (Phase 4):
   - Production hardening
   - Multi-cluster support
   - Advanced features (scheduling, alerting, etc.)

## Questions & Considerations

### Persistent Storage
- **Question**: Where to store investigation results?
- **Options**:
  - PersistentVolume in K8s
  - Object storage (S3, GCS, Azure Blob)
  - Database (PostgreSQL)
- **Decision**: TBD based on requirements

### Scaling Strategy
- **Question**: How many concurrent investigations?
- **Considerations**:
  - LLM API rate limits
  - Cost per investigation
  - Resource constraints
- **Decision**: Start with 5 concurrent jobs, tune based on usage

### Multi-Tenancy
- **Question**: Support multiple teams/organizations?
- **Considerations**:
  - Namespace isolation
  - Separate API keys per tenant
  - Cost allocation
- **Decision**: Single tenant for Phase 1, multi-tenant in Phase 4

## Resources

- Original OATS docs: [README.md](./README.md)
- Backend API docs: [services/backend-api/app/main.py](services/backend-api/app/main.py)
- Infrastructure docs: [infra/README.md](infra/README.md)
- Agent entrypoint: [services/agent/agent/main.py](services/agent/agent/main.py)

---

**Last Updated**: Phase 1 structure creation complete
**Next Milestone**: Link existing code and test Docker builds
