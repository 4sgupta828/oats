#!/usr/bin/env python3
"""
Generated UFs Management Tool
"""

import os
import sys
import json
import argparse
from datetime import datetime

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Change to the UFFLOW directory
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from uf_generator import uf_generator
except ImportError:
    # If running as a module, try relative import
    from .uf_generator import uf_generator

def list_ufs():
    """List all generated UFs."""
    ufs = uf_generator.list_generated_ufs()
    
    if not ufs:
        print("No generated UFs found.")
        return
    
    print(f"Found {len(ufs)} generated UFs:")
    print("-" * 80)
    
    for uf in ufs:
        print(f"ID: {uf.get('uf_id', 'Unknown')}")
        print(f"Created: {uf.get('created_at', 'Unknown')}")
        print(f"Task: {uf.get('task_description', 'Unknown')[:60]}...")
        print(f"Script File: {uf.get('script_file', 'Unknown')}")
        print(f"Test File: {uf.get('test_file', 'None')}")
        print("-" * 80)

def show_uf(uf_id: str):
    """Show details of a specific UF."""
    uf_data = uf_generator.load_uf(uf_id)
    
    if not uf_data:
        print(f"UF '{uf_id}' not found.")
        return
    
    print(f"UF ID: {uf_data['uf_id']}")
    print(f"Created: {uf_data['created_at']}")
    print(f"Task: {uf_data['task_description']}")
    print(f"UF File: {uf_data.get('uf_file', uf_data.get('file_path', 'Unknown'))}")
    print(f"Script File: {uf_data.get('script_file', 'Unknown')}")
    print(f"Test File: {uf_data.get('test_file', 'None')}")
    print(f"Constraints: {json.dumps(uf_data['constraints'], indent=2)}")
    print(f"Validation: {uf_data['validation']}")
    print("\nScript Content:")
    print("-" * 40)
    print(uf_data['script_content'])
    print("-" * 40)
    if uf_data.get('test_content'):
        print("\nTest Content:")
        print("-" * 40)
        print(uf_data['test_content'])
        print("-" * 40)

def delete_uf(uf_id: str):
    """Delete a specific UF."""
    if uf_generator.delete_uf(uf_id):
        print(f"✅ Deleted UF: {uf_id}")
    else:
        print(f"❌ Failed to delete UF: {uf_id}")

def clean_old_ufs(days: int = 30):
    """Clean up UFs older than specified days."""
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days)
    ufs = uf_generator.list_generated_ufs()
    
    deleted_count = 0
    for uf in ufs:
        created_at = datetime.fromisoformat(uf['created_at'])
        if created_at < cutoff_date:
            if uf_generator.delete_uf(uf['uf_id']):
                deleted_count += 1
                print(f"Deleted old UF: {uf['uf_id']}")
    
    print(f"Cleaned up {deleted_count} UFs older than {days} days.")

def main():
    parser = argparse.ArgumentParser(description="Manage generated UFs")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    subparsers.add_parser('list', help='List all generated UFs')
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show details of a specific UF')
    show_parser.add_argument('uf_id', help='UF ID to show')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a specific UF')
    delete_parser.add_argument('uf_id', help='UF ID to delete')
    
    # Clean command
    clean_parser = subparsers.add_parser('clean', help='Clean up old UFs')
    clean_parser.add_argument('--days', type=int, default=30, help='Delete UFs older than this many days')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        list_ufs()
    elif args.command == 'show':
        show_uf(args.uf_id)
    elif args.command == 'delete':
        delete_uf(args.uf_id)
    elif args.command == 'clean':
        clean_old_ufs(args.days)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
