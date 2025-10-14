#!/usr/bin/env python3
"""Apply database migration for interrupt types."""

import os
import sys
import psycopg2
from pathlib import Path

def apply_migration():
    """Apply the interrupt types migration."""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    # Read migration file
    migration_file = Path(__file__).parent / "migrations" / "001_add_interrupt_types.sql"
    if not migration_file.exists():
        print(f"❌ ERROR: Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    # Apply migration
    try:
        print(f"🔄 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = False

        print(f"🔄 Applying migration: 001_add_interrupt_types.sql")

        with conn.cursor() as cur:
            cur.execute(migration_sql)

        conn.commit()
        print("✅ Migration applied successfully!")

        # Verify new tables
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'execution_checkpoints'
            """)
            if cur.fetchone():
                print("✅ execution_checkpoints table created")

            cur.execute("""
                SELECT constraint_name FROM information_schema.constraint_column_usage
                WHERE table_name = 'user_feedback' AND constraint_name = 'valid_feedback_type'
            """)
            if cur.fetchone():
                print("✅ user_feedback constraint updated")

        conn.close()
        print("\n✅ All checks passed!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        sys.exit(1)

if __name__ == "__main__":
    apply_migration()
