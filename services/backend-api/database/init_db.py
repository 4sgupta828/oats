#!/usr/bin/env python3
"""Initialize OATS database schema."""

import psycopg2
import os
import sys
from pathlib import Path

def init_database(connection_string: str):
    """Initialize database with schema."""
    print(f"Connecting to database...")

    try:
        conn = psycopg2.connect(connection_string)
        print("✅ Connected to database")

        # Read schema file
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        print("Executing schema...")
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("✅ Schema initialized successfully")

        # Verify tables were created
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE 'agent_%'
            """)
            tables = cur.fetchall()

        print(f"\nCreated tables:")
        for table in tables:
            print(f"  - {table[0]}")

        conn.close()
        print("\n✅ Database initialization complete!")

    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)

def main():
    """Main entry point."""
    connection_string = os.getenv("DATABASE_URL")

    if not connection_string:
        print("❌ DATABASE_URL environment variable not set")
        print("\nUsage:")
        print("  export DATABASE_URL='postgresql://user:password@host:port/database'")
        print("  python init_db.py")
        sys.exit(1)

    print("OATS Database Initialization")
    print("=" * 50)
    print(f"Database: {connection_string.split('@')[-1] if '@' in connection_string else connection_string}")
    print("=" * 50)
    print()

    init_database(connection_string)

if __name__ == "__main__":
    main()
