#!/usr/bin/env python3
"""
Simple script to run all OATS services locally for development
"""
import subprocess
import sys
import time
import signal
import os

processes = []

def cleanup(signum=None, frame=None):
    """Kill all child processes"""
    print("\nShutting down all services...")
    for p in processes:
        try:
            p.terminate()
        except:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except:
            p.kill()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    os.chdir('/Users/sgupta/oats')

    # Check if venv exists
    venv_python = '/Users/sgupta/oats/venv/bin/python3'
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found at /Users/sgupta/oats/venv")
        print("Please create it with: python3 -m venv venv && source venv/bin/activate && pip install -r services/agent/requirements.txt -r services/backend-api/requirements.txt")
        sys.exit(1)

    print("Starting OATS services...")
    print("=" * 60)

    # 1. Start integrated backend (with embedded agent)
    print("1. Starting Backend with embedded Agent (localhost:8000)...")
    backend_process = subprocess.Popen(
        [venv_python, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
        cwd='/Users/sgupta/oats/services/backend-api',
        env={**os.environ, 'PYTHONPATH': '/Users/sgupta/oats/services/agent:/Users/sgupta/oats/services/backend-api'}
    )
    processes.append(backend_process)
    time.sleep(3)  # Wait for backend to start

    # 2. Start UI
    print("2. Starting UI (localhost:3000)...")
    ui_process = subprocess.Popen(
        ['npm', 'start'],
        cwd='/Users/sgupta/oats/services/ui'
    )
    processes.append(ui_process)

    print("=" * 60)
    print("All services started!")
    print("UI available at: http://localhost:3000")
    print("Press Ctrl+C to stop all services")
    print("=" * 60)

    # Wait for any process to exit
    try:
        while True:
            for p in processes:
                if p.poll() is not None:
                    print(f"Process {p.pid} exited")
                    cleanup()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
