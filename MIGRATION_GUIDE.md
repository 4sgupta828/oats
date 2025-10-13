# Event-Driven Architecture Migration Guide

This guide explains how to migrate from the WebSocket-based architecture to the new event-driven architecture with PostgreSQL and Server-Sent Events.

## 🎯 **Migration Overview**

### **What's Changing:**
- **Backend**: WebSocket → FastAPI + Server-Sent Events + PostgreSQL
- **Frontend**: Socket.IO → Native EventSource (SSE)
- **Communication**: Bidirectional WebSocket → Unidirectional SSE + HTTP
- **State Management**: In-memory → Persistent PostgreSQL event store

### **Benefits:**
- ✅ **Persistent executions** - survive restarts
- ✅ **User interruptions** - pause/resume executions
- ✅ **Multiple clients** - share execution URLs
- ✅ **Audit trail** - complete event history
- ✅ **Better scaling** - stateless backend design
- ✅ **User input support** - LLM can request user feedback

## 📋 **Migration Steps**

### **Step 1: Database Setup**

1. **Install PostgreSQL** (if not already installed):
   ```bash
   # macOS
   brew install postgresql
   brew services start postgresql
   
   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib
   sudo systemctl start postgresql
   ```

2. **Create database and user**:
   ```sql
   CREATE DATABASE oats;
   CREATE USER oats_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE oats TO oats_user;
   ```

3. **Set environment variable**:
   ```bash
   export DATABASE_URL="postgresql://oats_user:your_password@localhost:5432/oats"
   ```

4. **Initialize database schema**:
   ```bash
   cd services/backend-api
   python database/init_db.py
   ```

### **Step 2: Backend Migration**

1. **Install new dependencies**:
   ```bash
   cd services/backend-api
   pip install -r requirements.txt
   ```

2. **Test the new backend**:
   ```bash
   # Test database and event store
   python test_event_backend.py
   
   # Start the new backend
   python app/main_sse.py
   ```

3. **Verify health check**:
   ```bash
   curl http://localhost:8000/health
   ```

### **Step 3: Frontend Migration**

1. **Install frontend dependencies**:
   ```bash
   cd services/ui
   npm install
   ```

2. **Test the new frontend**:
   ```bash
   # Start with SSE version
   npm start
   # Then visit http://localhost:3000
   ```

3. **Switch to SSE version** (optional):
   ```bash
   # Replace App.js with AppSSE.js
   mv src/App.js src/App_websocket.js
   mv src/AppSSE.js src/App.js
   
   # Replace index.js with index_sse.js
   mv src/index.js src/index_websocket.js
   mv src/index_sse.js src/index.js
   ```

### **Step 4: Integration Testing**

1. **Run integration tests**:
   ```bash
   cd services/backend-api
   python test_integration.py
   ```

2. **Test complete workflow**:
   - Start backend: `python app/main_sse.py`
   - Start frontend: `npm start`
   - Submit a goal and verify events are streamed
   - Test user interruption functionality

### **Step 5: Deployment Migration**

1. **Build new Docker images**:
   ```bash
   # Backend
   docker build -f docker/Dockerfile.sse -t oats-backend-api-sse:latest .
   
   # Frontend (no changes needed)
   docker build -t oats-ui:latest .
   ```

2. **Update Kubernetes deployments**:
   ```bash
   # Apply new backend deployment
   kubectl apply -f infra/base/backend-api-sse-deployment.yaml
   
   # Update service to point to new backend
   kubectl patch service oats-backend-api -p '{"spec":{"selector":{"app":"oats-backend-api-sse"}}}'
   ```

3. **Verify deployment**:
   ```bash
   kubectl get pods -l app=oats-backend-api-sse
   kubectl logs -l app=oats-backend-api-sse
   ```

## 🔄 **Rollback Plan**

If issues arise, you can quickly rollback:

### **Backend Rollback:**
```bash
# Revert to WebSocket backend
kubectl patch service oats-backend-api -p '{"spec":{"selector":{"app":"oats-backend-api"}}}'
kubectl delete deployment oats-backend-api-sse
```

### **Frontend Rollback:**
```bash
# Revert to WebSocket frontend
cd services/ui
mv src/App.js src/AppSSE.js
mv src/App_websocket.js src/App.js
mv src/index.js src/index_sse.js
mv src/index_websocket.js src/index.js
```

## 🧪 **Testing Checklist**

### **Backend Tests:**
- [ ] Database connection and schema creation
- [ ] Event store operations (create, emit, retrieve)
- [ ] FastAPI endpoints (health, executions, events, feedback)
- [ ] Agent execution with event emission
- [ ] SSE streaming functionality

### **Frontend Tests:**
- [ ] SSE connection and reconnection
- [ ] Event parsing and display
- [ ] User input dialogs
- [ ] Approval dialogs
- [ ] Execution interruption
- [ ] Error handling

### **Integration Tests:**
- [ ] Complete execution workflow
- [ ] Multiple concurrent executions
- [ ] User feedback submission
- [ ] Execution pause/resume
- [ ] Error recovery

## 📊 **Performance Considerations**

### **Database Optimization:**
```sql
-- Monitor query performance
SELECT * FROM pg_stat_activity WHERE query LIKE '%agent_events%';

-- Check index usage
SELECT * FROM pg_stat_user_indexes WHERE relname = 'agent_events';
```

### **Connection Pooling:**
- Event store uses connection pooling (default: 10 connections)
- Adjust pool size based on concurrent executions
- Monitor connection usage with PostgreSQL logs

### **Event Retention:**
- Consider implementing event cleanup for old executions
- Archive completed executions after N days
- Monitor database growth

## 🔧 **Configuration**

### **Environment Variables:**
```bash
# Required
DATABASE_URL=postgresql://user:password@host:port/database

# Optional
EVENT_STORE_POOL_SIZE=10
MAX_CONCURRENT_EXECUTIONS=50
EVENT_RETENTION_DAYS=30
```

### **Database Configuration:**
```sql
-- Recommended PostgreSQL settings
shared_preload_libraries = 'pg_stat_statements'
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
```

## 🚨 **Troubleshooting**

### **Common Issues:**

1. **Database Connection Failed**:
   ```bash
   # Check PostgreSQL status
   pg_isready -h localhost -p 5432
   
   # Check connection string
   echo $DATABASE_URL
   ```

2. **SSE Connection Issues**:
   ```bash
   # Test SSE endpoint directly
   curl -N http://localhost:8000/executions/{execution_id}/events
   ```

3. **Event Store Errors**:
   ```bash
   # Check database logs
   tail -f /var/log/postgresql/postgresql-*.log
   ```

4. **Agent Execution Failures**:
   ```bash
   # Check agent logs
   kubectl logs -l app=oats-backend-api-sse
   ```

### **Monitoring:**
```bash
# Monitor executions
kubectl exec -it deployment/oats-backend-api-sse -- python -c "
from database.event_store import AsyncEventStore
import asyncio
async def monitor():
    store = AsyncEventStore('$DATABASE_URL')
    await store.initialize()
    executions = await store.list_executions(limit=10)
    print(f'Recent executions: {len(executions)}')
asyncio.run(monitor())
"
```

## 📈 **Success Metrics**

### **Key Performance Indicators:**
- **Execution Success Rate**: >95%
- **Event Processing Latency**: <100ms
- **SSE Connection Stability**: >99%
- **Database Query Performance**: <50ms average
- **User Satisfaction**: Improved UX with interruptions

### **Monitoring Dashboard:**
Create a monitoring dashboard with:
- Active executions count
- Event processing rate
- Error rates by component
- Database connection pool usage
- SSE connection count

## 🎉 **Migration Complete!**

Once all tests pass and the system is running smoothly:

1. **Update documentation** with new architecture details
2. **Train team** on new event-driven patterns
3. **Monitor performance** for the first few days
4. **Plan cleanup** of old WebSocket code after validation period

The new event-driven architecture provides a solid foundation for scaling the OATS agent system with better reliability, user experience, and maintainability.

---

**Need Help?** Check the troubleshooting section or review the test scripts for examples of proper usage.
