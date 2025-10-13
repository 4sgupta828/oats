#!/usr/bin/env python3
"""Database initialization script for OATS Agent Event-Driven Architecture."""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

async def init_database():
    """Initialize the database with schema and sample data."""
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("Example: export DATABASE_URL='postgresql://user:password@localhost/oats'")
        sys.exit(1)
    
    print(f"🔗 Connecting to database: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(database_url)
        print("✅ Connected to database")
        
        # Read and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            print(f"❌ Schema file not found: {schema_path}")
            sys.exit(1)
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        print("📝 Executing schema...")
        await conn.execute(schema_sql)
        print("✅ Schema executed successfully")
        
        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('agent_executions', 'agent_events', 'user_feedback')
            ORDER BY table_name
        """)
        
        print(f"✅ Created {len(tables)} tables:")
        for table in tables:
            print(f"   - {table['table_name']}")
        
        # Check indexes
        indexes = await conn.fetch("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename IN ('agent_executions', 'agent_events', 'user_feedback')
            ORDER BY tablename, indexname
        """)
        
        print(f"✅ Created {len(indexes)} indexes:")
        for idx in indexes:
            print(f"   - {idx['indexname']} on {idx['tablename']}")
        
        # Test basic operations
        print("🧪 Testing basic operations...")
        
        # Test execution creation
        execution_id = await conn.fetchval("""
            INSERT INTO agent_executions (goal, status, max_turns)
            VALUES ($1, $2, $3)
            RETURNING id
        """, "Test execution", "completed", 5)
        
        print(f"✅ Created test execution: {execution_id}")
        
        # Test event emission
        await conn.execute("""
            INSERT INTO agent_events (execution_id, turn_number, event_type, event_data, success)
            VALUES ($1, $2, $3, $4, $5)
        """, execution_id, 1, "execution_started", '{"goal": "Test execution"}', True)
        
        print("✅ Emitted test event")
        
        # Test event retrieval
        events = await conn.fetch("""
            SELECT event_type, success FROM agent_events WHERE execution_id = $1
        """, execution_id)
        
        print(f"✅ Retrieved {len(events)} events")
        
        # Test feedback submission
        await conn.execute("""
            INSERT INTO user_feedback (execution_id, turn_number, feedback_type, feedback_data)
            VALUES ($1, $2, $3, $4)
        """, execution_id, 1, "input", '{"input": "test input"}')
        
        print("✅ Submitted test feedback")
        
        # Clean up test data
        await conn.execute("DELETE FROM agent_executions WHERE id = $1", execution_id)
        print("✅ Cleaned up test data")
        
        await conn.close()
        print("🎉 Database initialization completed successfully!")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(init_database())
