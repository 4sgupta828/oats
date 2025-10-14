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

def load_env_file(env_path):
    """Load environment variables from .env file"""
    env_vars = {}
    if os.path.exists(env_path):
        print(f"Loading environment from {env_path}")
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

def check_postgres():
    """Check if PostgreSQL is running locally"""
    try:
        import getpass
        db_user = getpass.getuser()
        # Try to find psql in common locations
        psql_paths = [
            'psql',  # If in PATH
            '/opt/homebrew/opt/postgresql@15/bin/psql',
            '/usr/local/bin/psql',
        ]
        for psql in psql_paths:
            try:
                result = subprocess.run(
                    [psql, '-U', db_user, '-d', 'postgres', '-c', 'SELECT 1'],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False

def cleanup_port(port):
    """Kill any process using the specified port"""
    try:
        # Find process using the port
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"   Killing process {pid} on port {port}...")
                    subprocess.run(['kill', '-9', pid], capture_output=True)
            return True
        return False
    except Exception as e:
        print(f"   Warning: Could not cleanup port {port}: {e}")
        return False

def cleanup_ports(ports):
    """Clean up multiple ports before starting services"""
    print("\n" + "=" * 60)
    print("Checking for existing services on required ports...")
    print("=" * 60)

    cleaned = False
    for port in ports:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f" Port {port} is in use, stopping existing process...")
            if cleanup_port(port):
                cleaned = True
        else:
            print(f"✅ Port {port} is available")

    if cleaned:
        print("\n✅ Ports cleaned up successfully")
        time.sleep(1)  # Give OS time to release ports

def setup_local_database(venv_python, project_root, env_vars):
    """Set up local PostgreSQL database for OATS"""
    print("\n" + "=" * 60)
    print("Setting up local PostgreSQL database...")
    print("=" * 60)

    # Default local database URL (adjust username/password as needed)
    import getpass
    db_user = getpass.getuser()
    default_db_url = f"postgresql://{db_user}@localhost:5432/oats"
    db_url = env_vars.get('DATABASE_URL', default_db_url)

    # Initialize database schema
    init_db_path = os.path.join(project_root, 'services/backend-api/database/init_db.py')
    if os.path.exists(init_db_path):
        print(f"Initializing database with schema...")
        init_env = {**os.environ, **env_vars, 'DATABASE_URL': db_url}

        result = subprocess.run(
            [venv_python, init_db_path],
            env=init_env,
            cwd=project_root
        )

        if result.returncode != 0:
            print("\n⚠️  Database initialization failed!")
            print("Please ensure:")
            print("  1. PostgreSQL is running locally (brew services start postgresql@15)")
            print(f"  2. Database 'oats' exists (or create it with: createdb oats)")
            print(f"  3. Database URL is correct: {db_url}")
            response = input("\nContinue anyway? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
        else:
            print("✅ Database initialized successfully")

    return db_url

def main():
    project_root = os.getcwd()
    venv_python = os.path.join(project_root, 'venv/bin/python3')

    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please create it first.")
        sys.exit(1)

    print("=" * 60)
    print("Starting OATS services for local development...")
    print("=" * 60)

    # Clean up ports that will be used
    cleanup_ports([8000, 3000])

    # Load environment variables from .env file
    env_file = os.path.join(project_root, '.env')
    env_vars = load_env_file(env_file)

    # Set up local database
    db_url = setup_local_database(venv_python, project_root, env_vars)

    print("\n" + "=" * 60)
    print("Starting services...")
    print("=" * 60)

    # 1. Start the integrated Backend API (with embedded Agent)
    print("\n1. Starting Backend API on localhost:8000...")
    backend_env = {
        **os.environ,
        **env_vars,
        'PYTHONPATH': f"{project_root}/services/agent:{project_root}/services/backend-api",
        'DATABASE_URL': db_url
    }
    # Note: --reload is disabled to prevent disconnections when agent creates files
    # To enable hot-reload during development, add '--reload' flag back
    backend_process = subprocess.Popen(
        [
            venv_python, '-m', 'uvicorn', 'app.main:app',
            '--host', '0.0.0.0', '--port', '8000'
        ],
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
