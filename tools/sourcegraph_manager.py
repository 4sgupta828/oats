#!/usr/bin/env python3
"""
Sourcegraph Manager for UF Flow
Manages Sourcegraph git server and local search tools for the current repository.
"""

import os
import sys
import subprocess
import signal
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

class SourcegraphManager:
    """Manages Sourcegraph services for the current repository."""
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize Sourcegraph manager.
        
        Args:
            repo_path: Path to repository (defaults to current directory)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.repo_name = self.repo_path.name
        self.git_server_port = 3434
        self.search_ui_port = 8081
        
        # Process IDs for tracking
        self.git_server_pid: Optional[int] = None
        self.search_ui_pid: Optional[int] = None
        
        # PID file locations
        self.pid_dir = Path.home() / '.sourcegraph_manager'
        self.pid_dir.mkdir(exist_ok=True)
        self.git_server_pid_file = self.pid_dir / f'{self.repo_name}_git_server.pid'
        self.search_ui_pid_file = self.pid_dir / f'{self.repo_name}_search_ui.pid'
    
    def get_repo_info(self) -> Dict[str, Any]:
        """Get information about the current repository."""
        try:
            # Get git remote info
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            remote_url = result.stdout.strip()
        except subprocess.CalledProcessError:
            remote_url = "No remote configured"
        
        try:
            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
        except subprocess.CalledProcessError:
            current_branch = "Unknown"
        
        try:
            # Get commit count
            result = subprocess.run(
                ['git', 'rev-list', '--count', 'HEAD'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            commit_count = int(result.stdout.strip())
        except subprocess.CalledProcessError:
            commit_count = 0
        
        return {
            "repo_name": self.repo_name,
            "repo_path": str(self.repo_path),
            "remote_url": remote_url,
            "current_branch": current_branch,
            "commit_count": commit_count,
            "is_git_repo": (self.repo_path / '.git').exists()
        }
    
    def start_git_server(self) -> bool:
        """Start Sourcegraph git server for the repository."""
        if self.is_git_server_running():
            print(f"✅ Git server already running for {self.repo_name}")
            return True
        
        try:
            # Start git server
            cmd = [
                'src', 'serve-git',
                '-addr', f':{self.git_server_port}',
                str(self.repo_path)
            ]
            
            print(f"🚀 Starting git server for {self.repo_name}...")
            print(f"   Command: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait a moment to see if it starts successfully
            time.sleep(2)
            
            if process.poll() is None:  # Still running
                self.git_server_pid = process.pid
                self._save_pid(self.git_server_pid_file, process.pid)
                print(f"✅ Git server started (PID: {process.pid})")
                print(f"   Serving: {self.repo_path}")
                print(f"   URL: http://localhost:{self.git_server_port}")
                return True
            else:
                stdout, stderr = process.communicate()
                print(f"❌ Failed to start git server:")
                print(f"   STDOUT: {stdout}")
                print(f"   STDERR: {stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error starting git server: {e}")
            return False
    
    def start_search_ui(self) -> bool:
        """Start local search UI."""
        if self.is_search_ui_running():
            print(f"✅ Search UI already running for {self.repo_name}")
            return True
        
        try:
            # Start search UI
            cmd = [
                'python3', 'tools/simple_search_ui.py',
                str(self.search_ui_port)
            ]
            
            print(f"🌐 Starting search UI for {self.repo_name}...")
            print(f"   Command: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                cwd=self.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait a moment to see if it starts successfully
            time.sleep(3)
            
            if process.poll() is None:  # Still running
                self.search_ui_pid = process.pid
                self._save_pid(self.search_ui_pid_file, process.pid)
                print(f"✅ Search UI started (PID: {process.pid})")
                print(f"   URL: http://localhost:{self.search_ui_port}")
                return True
            else:
                stdout, stderr = process.communicate()
                print(f"❌ Failed to start search UI:")
                print(f"   STDOUT: {stdout}")
                print(f"   STDERR: {stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error starting search UI: {e}")
            return False
    
    def stop_git_server(self) -> bool:
        """Stop git server."""
        pid = self._load_pid(self.git_server_pid_file)
        if not pid:
            print(f"ℹ️  No git server PID found for {self.repo_name}")
            return True
        
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            
            # Check if it's still running
            try:
                os.kill(pid, 0)  # Check if process exists
                # Still running, force kill
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            except ProcessLookupError:
                pass  # Process already dead
            
            self._remove_pid(self.git_server_pid_file)
            print(f"✅ Git server stopped (PID: {pid})")
            return True
            
        except ProcessLookupError:
            print(f"ℹ️  Git server was not running (PID: {pid})")
            self._remove_pid(self.git_server_pid_file)
            return True
        except Exception as e:
            print(f"❌ Error stopping git server: {e}")
            return False
    
    def stop_search_ui(self) -> bool:
        """Stop search UI."""
        pid = self._load_pid(self.search_ui_pid_file)
        if not pid:
            print(f"ℹ️  No search UI PID found for {self.repo_name}")
            return True
        
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            
            # Check if it's still running
            try:
                os.kill(pid, 0)  # Check if process exists
                # Still running, force kill
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            except ProcessLookupError:
                pass  # Process already dead
            
            self._remove_pid(self.search_ui_pid_file)
            print(f"✅ Search UI stopped (PID: {pid})")
            return True
            
        except ProcessLookupError:
            print(f"ℹ️  Search UI was not running (PID: {pid})")
            self._remove_pid(self.search_ui_pid_file)
            return True
        except Exception as e:
            print(f"❌ Error stopping search UI: {e}")
            return False
    
    def is_git_server_running(self) -> bool:
        """Check if git server is running."""
        pid = self._load_pid(self.git_server_pid_file)
        if not pid:
            return False
        
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except ProcessLookupError:
            self._remove_pid(self.git_server_pid_file)
            return False
    
    def is_search_ui_running(self) -> bool:
        """Check if search UI is running."""
        pid = self._load_pid(self.search_ui_pid_file)
        if not pid:
            return False
        
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except ProcessLookupError:
            self._remove_pid(self.search_ui_pid_file)
            return False
    
    def status(self) -> Dict[str, Any]:
        """Get status of all services."""
        repo_info = self.get_repo_info()
        
        return {
            **repo_info,
            "services": {
                "git_server": {
                    "running": self.is_git_server_running(),
                    "pid": self._load_pid(self.git_server_pid_file),
                    "port": self.git_server_port,
                    "url": f"http://localhost:{self.git_server_port}"
                },
                "search_ui": {
                    "running": self.is_search_ui_running(),
                    "pid": self._load_pid(self.search_ui_pid_file),
                    "port": self.search_ui_port,
                    "url": f"http://localhost:{self.search_ui_port}"
                }
            }
        }
    
    def start_all(self) -> bool:
        """Start all services."""
        print(f"🚀 Starting Sourcegraph services for {self.repo_name}")
        print("=" * 50)
        
        repo_info = self.get_repo_info()
        print(f"📁 Repository: {repo_info['repo_name']}")
        print(f"📍 Path: {repo_info['repo_path']}")
        print(f"🌿 Branch: {repo_info['current_branch']}")
        print(f"🔗 Remote: {repo_info['remote_url']}")
        print(f"📊 Commits: {repo_info['commit_count']}")
        print()
        
        if not repo_info['is_git_repo']:
            print("❌ Not a git repository!")
            return False
        
        success = True
        success &= self.start_git_server()
        success &= self.start_search_ui()
        
        if success:
            print()
            print("🎉 All services started successfully!")
            print(f"🔍 Search UI: http://localhost:{self.search_ui_port}")
            print(f"📡 Git Server: http://localhost:{self.git_server_port}")
        
        return success
    
    def stop_all(self) -> bool:
        """Stop all services."""
        print(f"⏹️  Stopping Sourcegraph services for {self.repo_name}")
        print("=" * 50)
        
        success = True
        success &= self.stop_git_server()
        success &= self.stop_search_ui()
        
        if success:
            print()
            print("✅ All services stopped successfully!")
        
        return success
    
    def _save_pid(self, pid_file: Path, pid: int):
        """Save process ID to file."""
        try:
            pid_file.write_text(str(pid))
        except Exception as e:
            print(f"Warning: Could not save PID to {pid_file}: {e}")
    
    def _load_pid(self, pid_file: Path) -> Optional[int]:
        """Load process ID from file."""
        try:
            if pid_file.exists():
                return int(pid_file.read_text().strip())
        except Exception:
            pass
        return None
    
    def _remove_pid(self, pid_file: Path):
        """Remove PID file."""
        try:
            if pid_file.exists():
                pid_file.unlink()
        except Exception:
            pass

def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage Sourcegraph services for UF Flow')
    parser.add_argument('command', choices=['start', 'stop', 'status', 'restart'], 
                       help='Command to execute')
    parser.add_argument('--repo', '-r', help='Repository path (default: current directory)')
    parser.add_argument('--json', '-j', action='store_true', help='Output status as JSON')
    
    args = parser.parse_args()
    
    manager = SourcegraphManager(args.repo)
    
    if args.command == 'start':
        success = manager.start_all()
        sys.exit(0 if success else 1)
    
    elif args.command == 'stop':
        success = manager.stop_all()
        sys.exit(0 if success else 1)
    
    elif args.command == 'restart':
        manager.stop_all()
        time.sleep(2)
        success = manager.start_all()
        sys.exit(0 if success else 1)
    
    elif args.command == 'status':
        status = manager.status()
        
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"📊 Sourcegraph Status for {status['repo_name']}")
            print("=" * 50)
            print(f"📁 Repository: {status['repo_name']}")
            print(f"📍 Path: {status['repo_path']}")
            print(f"🌿 Branch: {status['current_branch']}")
            print(f"🔗 Remote: {status['remote_url']}")
            print(f"📊 Commits: {status['commit_count']}")
            print(f"🔧 Git Repo: {'✅ Yes' if status['is_git_repo'] else '❌ No'}")
            print()
            
            services = status['services']
            print("🔧 Services:")
            for service_name, service_info in services.items():
                status_icon = "✅" if service_info['running'] else "❌"
                print(f"  {status_icon} {service_name.replace('_', ' ').title()}")
                if service_info['running']:
                    print(f"     PID: {service_info['pid']}")
                    print(f"     URL: {service_info['url']}")
                else:
                    print(f"     Status: Stopped")

if __name__ == "__main__":
    main()
