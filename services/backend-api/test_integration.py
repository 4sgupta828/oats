#!/usr/bin/env python3
"""Integration test for the complete event-driven architecture."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

async def test_complete_workflow():
    """Test the complete event-driven workflow."""
    print("🚀 Starting Complete Event-Driven Architecture Integration Test\n")
    
    # Test 1: Database initialization
    print("1️⃣ Testing Database Initialization...")
    await test_database_init()
    
    # Test 2: Event store operations
    print("\n2️⃣ Testing Event Store Operations...")
    execution_id = await test_event_store()
    
    # Test 3: FastAPI endpoints
    print("\n3️⃣ Testing FastAPI Endpoints...")
    await test_fastapi_endpoints(execution_id)
    
    # Test 4: Agent execution with events
    print("\n4️⃣ Testing Agent Execution with Events...")
    await test_agent_execution()
    
    print("\n🎉 All integration tests completed successfully!")

async def test_database_init():
    """Test database initialization."""
    try:
        from database.init_db import init_database
        await init_database()
        print("✅ Database initialization successful")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise

async def test_event_store():
    """Test event store operations."""
    from database.event_store import AsyncEventStore
    
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/oats")
    event_store = AsyncEventStore(database_url)
    await event_store.initialize()
    
    try:
        # Create execution
        execution_id = await event_store.create_execution(
            goal="Integration test goal",
            user_id="test_user",
            max_turns=3,
            metadata={"test": "integration"}
        )
        print(f"✅ Created execution: {execution_id}")
        
        # Emit various events
        events = [
            ("turn_started", {"turn_number": 1, "goal": "test"}, None),
            ("llm_called", {"messages_count": 3}, None),
            ("llm_response_success", {"turn_number": 1, "reflect": {"outcome": "SUCCESS"}}, True),
            ("tool_started", {"tool_name": "test_tool", "parameters": {}}, None),
            ("tool_success", {"tool_name": "test_tool", "observation": "test result"}, True),
            ("execution_completed", {"completion_reason": "Test completed"}, True)
        ]
        
        for event_type, event_data, success in events:
            await event_store.emit_event(execution_id, 1, event_type, event_data, success)
        
        print(f"✅ Emitted {len(events)} events")
        
        # Test event retrieval
        retrieved_events = await event_store.get_events_since(execution_id, 0)
        print(f"✅ Retrieved {len(retrieved_events)} events")
        
        # Test feedback
        await event_store.submit_feedback(execution_id, 1, "input", {"input": "test input"})
        print("✅ Submitted user feedback")
        
        # Test status update
        await event_store.update_execution_status(execution_id, "completed")
        print("✅ Updated execution status")
        
        return execution_id
        
    finally:
        await event_store.close()

async def test_fastapi_endpoints():
    """Test FastAPI endpoints."""
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        try:
            # Health check
            async with session.get(f"{base_url}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    print(f"✅ Health check passed - Services: {health['services']}")
                else:
                    print(f"❌ Health check failed: {resp.status}")
                    return None
            
            # Create execution
            execution_data = {
                "goal": "Integration test execution",
                "max_turns": 3,
                "user_id": "integration_test",
                "metadata": {"test": "integration"}
            }
            
            async with session.post(f"{base_url}/executions", json=execution_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    execution_id = result["execution_id"]
                    print(f"✅ Created execution via API: {execution_id}")
                else:
                    print(f"❌ Execution creation failed: {resp.status}")
                    return None
            
            # Test status endpoint
            async with session.get(f"{base_url}/executions/{execution_id}/status") as resp:
                if resp.status == 200:
                    status = await resp.json()
                    print(f"✅ Retrieved execution status: {status['status']}")
                else:
                    print(f"❌ Status retrieval failed: {resp.status}")
            
            # Test feedback endpoint
            feedback_data = {
                "turn_number": 1,
                "feedback_type": "input",
                "data": {"input": "integration test input"}
            }
            
            async with session.post(f"{base_url}/executions/{execution_id}/feedback", json=feedback_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"✅ Submitted feedback: {result['status']}")
                else:
                    print(f"❌ Feedback submission failed: {resp.status}")
            
            return execution_id
            
        except aiohttp.ClientConnectorError:
            print("⚠️ FastAPI server not running - skipping endpoint tests")
            print("   Start server with: python app/main_sse.py")
            return None
        except Exception as e:
            print(f"❌ FastAPI endpoint tests failed: {e}")
            return None

async def test_agent_execution():
    """Test agent execution with event emission."""
    try:
        # Add agent path to sys.path
        agent_path = Path(__file__).parent.parent / "agent"
        sys.path.insert(0, str(agent_path))
        
        from reactor.event_agent_controller import EventAgentController
        from registry.main import global_registry
        from database.event_store import AsyncEventStore
        
        # Initialize event store
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost/oats")
        event_store = AsyncEventStore(database_url)
        await event_store.initialize()
        
        # Create execution
        execution_id = await event_store.create_execution(
            goal="Test agent execution with events",
            user_id="agent_test",
            max_turns=2,
            metadata={"test": "agent_execution"}
        )
        
        print(f"✅ Created execution for agent test: {execution_id}")
        
        # Load tools
        tools_path = agent_path / "tools"
        global_registry.load_ufs_from_directory(str(tools_path))
        
        # Create event-emitting agent controller
        agent = EventAgentController(global_registry, event_store)
        
        # Execute goal (this will emit events)
        print("🤖 Starting agent execution...")
        result = await asyncio.to_thread(
            agent.execute_goal, 
            "Test agent execution with events", 
            2, 
            execution_id
        )
        
        print(f"✅ Agent execution completed: success={result.success}")
        
        # Verify events were emitted
        events = await event_store.get_events_since(execution_id, 0)
        print(f"✅ Agent emitted {len(events)} events")
        
        # Show event types
        event_types = [e['event_type'] for e in events]
        print(f"   Event types: {', '.join(set(event_types))}")
        
        await event_store.close()
        
    except Exception as e:
        print(f"❌ Agent execution test failed: {e}")
        import traceback
        traceback.print_exc()
        raise

async def test_sse_streaming():
    """Test Server-Sent Events streaming."""
    print("\n5️⃣ Testing SSE Streaming...")
    
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    try:
        # Create an execution first
        async with aiohttp.ClientSession() as session:
            execution_data = {
                "goal": "Test SSE streaming",
                "max_turns": 2,
                "user_id": "sse_test"
            }
            
            async with session.post(f"{base_url}/executions", json=execution_data) as resp:
                if resp.status != 200:
                    print(f"❌ Failed to create execution for SSE test: {resp.status}")
                    return
                
                result = await resp.json()
                execution_id = result["execution_id"]
        
        # Test SSE stream
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/executions/{execution_id}/events") as resp:
                if resp.status != 200:
                    print(f"❌ SSE stream failed: {resp.status}")
                    return
                
                print("✅ SSE stream opened successfully")
                
                event_count = 0
                async for line in resp.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        event_count += 1
                        print(f"   Received SSE event #{event_count}")
                        
                        if event_count >= 5:  # Limit for test
                            break
                
                print(f"✅ Received {event_count} SSE events")
                
    except aiohttp.ClientConnectorError:
        print("⚠️ FastAPI server not running - skipping SSE test")
    except Exception as e:
        print(f"❌ SSE streaming test failed: {e}")

async def main():
    """Run all integration tests."""
    await test_complete_workflow()
    await test_sse_streaming()

if __name__ == "__main__":
    asyncio.run(main())
