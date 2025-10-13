# Log Fetching Scripts

Scripts to download and stream logs from your OATS application running in AWS EKS.

## Available Scripts

### 1. `fetch-logs.sh` - Download Logs Once

Downloads the latest logs from your pods and saves them to disk.

**Usage:**
```bash
# Download to local logs/ directory (no sudo required)
./scripts/fetch-logs.sh

# Download to /logs directory (requires sudo)
sudo LOGS_DIR=/logs ./scripts/fetch-logs.sh
```

**Output:**
- `logs/agent.log` - Backend API logs (includes agent execution logs)
- `logs/ui.log` - UI server logs

**Features:**
- Downloads last 10,000 lines from each pod
- Auto-detects pod names
- Shows file size and line count
- Color-coded output

---

### 2. `fetch-logs-sudo.sh` - Download to /logs

Downloads logs directly to `/logs` directory (requires sudo/root).

**Usage:**
```bash
sudo ./scripts/fetch-logs-sudo.sh
```

**Output:**
- `/logs/agent.log` - Backend API logs
- `/logs/ui.log` - UI server logs

---

### 3. `stream-logs.sh` - Live Log Streaming

Stream logs in real-time while also saving to disk.

**Usage:**
```bash
# Stream both agent and UI logs
./scripts/stream-logs.sh both

# Stream only agent logs
./scripts/stream-logs.sh agent

# Stream only UI logs
./scripts/stream-logs.sh ui
```

**Features:**
- Real-time log streaming
- Color-coded by source (AGENT vs UI)
- Saves to disk while streaming
- Press Ctrl+C to stop

---

## Quick Commands

### View Downloaded Logs

```bash
# View agent logs
cat logs/agent.log

# View UI logs
cat logs/ui.log

# Tail agent logs (last 50 lines)
tail -n 50 logs/agent.log

# Search for errors in agent logs
grep -i error logs/agent.log

# Search for specific investigation ID
grep "investigation_id" logs/agent.log
```

### Direct kubectl Commands

```bash
# Get live logs from backend
kubectl logs -f -l app=oats-backend-api

# Get live logs from UI
kubectl logs -f -l app=oats-ui

# Get last 100 lines from backend
kubectl logs -l app=oats-backend-api --tail=100

# Get logs with timestamps
kubectl logs -l app=oats-backend-api --timestamps
```

---

## Pod Labels

The scripts use these labels to find pods:

- **Backend/Agent**: `app=oats-backend-api`
- **UI**: `app=oats-ui`

---

## Troubleshooting

### "No pods found"
- Check cluster connection: `kubectl get pods`
- Verify pods are running: `kubectl get pods -l app=oats-backend-api`

### Permission denied on /logs
- Use the local version: `./scripts/fetch-logs.sh`
- Or run with sudo: `sudo ./scripts/fetch-logs-sudo.sh`

### Logs are too large
- Reduce lines: Edit `--tail=10000` to a smaller number
- Stream specific pod: `kubectl logs <pod-name> --tail=100`

---

## Log Locations

| Script | Default Location |
|--------|------------------|
| `fetch-logs.sh` | `/Users/sgupta/oats/logs/` |
| `fetch-logs-sudo.sh` | `/logs/` |
| `stream-logs.sh` | `/Users/sgupta/oats/logs/` or `/logs/` |

---

## Examples

### Download logs for debugging
```bash
./scripts/fetch-logs.sh
cat logs/agent.log | grep ERROR
```

### Monitor logs during investigation
```bash
./scripts/stream-logs.sh agent
# In another terminal, trigger an investigation via UI
```

### Download and search for specific investigation
```bash
./scripts/fetch-logs.sh
grep "investigation_123" logs/agent.log
```

### Get logs from crashed pod
```bash
# Get pod name
POD=$(kubectl get pods -l app=oats-backend-api -o jsonpath='{.items[0].metadata.name}')

# Get logs from previous instance
kubectl logs $POD --previous > logs/agent-crashed.log
```

---

## Log Format

### Agent Logs (`agent.log`)
Contains:
- FastAPI server startup
- Socket.IO connections
- Investigation execution
- Tool calls and results
- LLM interactions
- Errors and warnings

### UI Logs (`ui.log`)
Contains:
- Nginx/static file serving logs
- HTTP request logs
- Access logs
- Server startup messages

---

## Automation

### Cron Job (Download logs every hour)
```bash
# Add to crontab
0 * * * * /Users/sgupta/oats/scripts/fetch-logs.sh

# Or with sudo (requires sudoers configuration)
0 * * * * sudo /Users/sgupta/oats/scripts/fetch-logs-sudo.sh
```

### Watch logs continuously
```bash
watch -n 10 '/Users/sgupta/oats/scripts/fetch-logs.sh && tail -n 20 logs/agent.log'
```

---

## Related Commands

See also [`DEPLOYMENT_SUCCESS.md`](/Users/sgupta/oats/DEPLOYMENT_SUCCESS.md) for more kubectl commands and cluster management.
