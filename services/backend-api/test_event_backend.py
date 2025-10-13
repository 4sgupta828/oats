#!/usr/bin/env python3
"""Test script for the event-driven backend."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

async def test_event_store():
    """Test the event store functionality."""
    print("🧪 Testing Event Store...")
    
    from database.event_store import AsyncEventStore
    
    # Get database URL
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/oats")
    print(f"🔗 Connecting to: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    # Initialize event store
    event_store = AsyncEventStore(database_url)
    await event_store.initialize()
    
    try:
        # Test execution creation
        execution_id = await event_store.create_execution(
            goal="Test goal for event-driven architecture",
            user_id="test_user",
            max_turns=5,
            metadata={"test": True, "version": "2.0.0"}
        )
        print(f"✅ Created execution: {execution_id}")
        
        # Test event emission
        await event_store.emit_event(
            execution_id, 1, "turn_started",
            {"turn_number": 1, "goal": "Test goal"}, True
        )
        print("✅ Emitted turn_started event")
        
        await event_store.emit_event(
            execution_id, 1, "llm_called",
            {"messages_count": 3, "model": "claude-3-5-sonnet"}, None
        )
        print("✅ Emitted llm_called event")
        
        await event_store.emit_event(
            execution_id, 1, "tool_started",
            {"tool_name": "test_tool", "parameters": {"param": "value"}}, None
        )
        print("✅ Emitted tool_started event")
        
        await event_store.emit_event(
            execution_id, 1, "tool_success",
            {"tool_name": "test_tool", "observation": "Test observation"}, True
        )
        print("✅ Emitted tool_success event")
        
        # Test event retrieval
        events = await event_store.get_events_since(execution_id, 0)
        print(f"✅ Retrieved {len(events)} events")
        
        for event in events:
            print(f"   - {event['event_type']} (turn {event['turn_number']})")
        
        # Test feedback submission
        await event_store.submit_feedback(
            execution_id, 1, "input", {"input": "test user input"}
        )
        print("✅ Submitted user feedback")
        
        # Test status update
        await event_store.update_execution_status(execution_id, "completed")
        print("✅ Updated execution status to completed")
        
        # Test execution summary
        summary = await event_store.get_execution_summary(execution_id)
        print(f"✅ Generated execution summary with {len(summary['event_counts'])} event types")
        
        # Clean up
        await event_store.close()
        print("✅ Event store test completed successfully!")
        
    except Exception as e:
        print(f"❌ Event store test failed: {e}")
        await event_store.close()
        raise

async def test_fastapi_endpoints():
    """Test FastAPI endpoints (requires running server)."""
    print("\n🧪 Testing FastAPI Endpoints...")
    
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test health check
            async with session.get(f"{base_url}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    print("✅ Health check passed")
                    print(f"   Services: {health['services']}")
                else:
                    print(f"❌ Health check failed: {resp.status}")
                    return
            
            # Test execution creation
            execution_data = {
                "goal": "Test execution via API",
                "max_turns": 3,
                "user_id": "test_user",
                "metadata": {"test": True}
            }
            
            async with session.post(f"{base_url}/executions", json=execution_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    execution_id = result["execution_id"]
                    print(f"✅ Created execution via API: {execution_id}")
                else:
                    print(f"❌ Execution creation failed: {resp.status}")
                    return
            
            # Test execution status
            async with session.get(f"{base_url}/executions/{execution_id}/status") as resp:
                if resp.status == 200:
                    status = await resp.json()
                    print(f"✅ Retrieved execution status: {status['status']}")
                else:
                    print(f"❌ Status retrieval failed: {resp.status}")
            
            # Test feedback submission
            feedback_data = {
                "turn_number": 1,
                "feedback_type": "input",
                "data": {"input": "test feedback"}
            }
            
            async with session.post(f"{base_url}/executions/{execution_id}/feedback", json=feedback_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"✅ Submitted feedback: {result['status']}")
                else:
                    print(f"❌ Feedback submission failed: {resp.status}")
            
            print("✅ FastAPI endpoint tests completed!")
            
        except aiohttp.ClientConnectorError:
            print("⚠️ FastAPI server not running - skipping endpoint tests")
            print("   Start server with: python app/main_sse.py")
        except Exception as e:
            print(f"❌ FastAPI endpoint tests failed: {e}")

async def main():
    """Run all tests."""
    print("🚀 Starting Event-Driven Backend Tests\n")
    
    # Test event store
    await test_event_store()
    
    # Test FastAPI endpoints (if server is running)
    await test_fastapi_endpoints()
    
    print("\n🎉 All tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
