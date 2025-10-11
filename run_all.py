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
        except Exception:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    project_root = os.getcwd()
    venv_python = os.path.join(project_root, 'venv/bin/python3')
    
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please create it first.")
        sys.exit(1)

    print("=" * 60)
    print("Starting OATS services for local development...")
    print("=" * 60)

    # 1. Start the integrated Backend API (with embedded Agent)
    print("1. Starting Backend API on localhost:8000...")
    backend_env = {
        **os.environ,
        'PYTHONPATH': f"{project_root}/services/agent:{project_root}/services/backend-api"
    }
    backend_process = subprocess.Popen(
        [venv_python, '-m', 'uvicorn', 'app.main:socket_app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
        cwd=os.path.join(project_root, 'services/backend-api'),
        env=backend_env
    )
    processes.append(backend_process)
    time.sleep(3)

    # 2. Start the UI development server
    print("2. Starting UI on localhost:3000...")
    ui_process = subprocess.Popen(['npm', 'start'], cwd=os.path.join(project_root, 'services/ui'))
    processes.append(ui_process)

    print("=" * 60)
    print("✅ All services started!")
    print("   UI available at: http://localhost:3000")
    print("Press Ctrl+C to stop all services.")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
