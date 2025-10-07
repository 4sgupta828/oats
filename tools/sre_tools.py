# tools/sre_tools.py
"""
SRE/Infrastructure troubleshooting tools for the OATS framework.
These tools support the Universal RCA Framework from prompt v3.
"""

import os
import sys
import logging
import subprocess
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput

logger = logging.getLogger(__name__)

# ============================================================================
# System Health Check Tools (Layer 1 & 2: Infrastructure & Runtime)
# ============================================================================

class CheckSystemHealthInput(UfInput):
    """Input for comprehensive system health check."""
    include_network: bool = Field(default=True, description="Include network connectivity checks")
    include_disk: bool = Field(default=True, description="Include disk space checks")
    include_memory: bool = Field(default=True, description="Include memory usage checks")
    include_cpu: bool = Field(default=True, description="Include CPU usage checks")

@uf(name="check_system_health", version="1.0.0",
   description="Comprehensive system health check covering Layer 1 (Infrastructure) and Layer 2 (Runtime). Returns status of disk, memory, CPU, and network.")
def check_system_health(inputs: CheckSystemHealthInput) -> dict:
    """Perform comprehensive system health check."""
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "overall_status": "HEALTHY",
            "warnings": [],
            "errors": []
        }

        # Check disk space
        if inputs.include_disk:
            try:
                disk_result = subprocess.run(
                    ["df", "-h"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                results["checks"]["disk"] = {
                    "status": "HEALTHY",
                    "output": disk_result.stdout
                }
                # Check for >85% usage
                for line in disk_result.stdout.split('\n'):
                    if '%' in line and 'Capacity' not in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            usage = parts[4].strip('%')
                            if usage.isdigit() and int(usage) > 85:
                                results["warnings"].append(f"Disk usage above 85%: {line.strip()}")
                                results["checks"]["disk"]["status"] = "WARNING"
            except Exception as e:
                results["checks"]["disk"] = {"status": "ERROR", "error": str(e)}
                results["errors"].append(f"Disk check failed: {e}")

        # Check memory
        if inputs.include_memory:
            try:
                mem_result = subprocess.run(
                    ["free", "-h"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if mem_result.returncode == 0:
                    results["checks"]["memory"] = {
                        "status": "HEALTHY",
                        "output": mem_result.stdout
                    }
                else:
                    # macOS doesn't have free command, use vm_stat
                    mem_result = subprocess.run(
                        ["vm_stat"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    results["checks"]["memory"] = {
                        "status": "HEALTHY",
                        "output": mem_result.stdout
                    }
            except Exception as e:
                results["checks"]["memory"] = {"status": "ERROR", "error": str(e)}
                results["errors"].append(f"Memory check failed: {e}")

        # Check CPU
        if inputs.include_cpu:
            try:
                cpu_result = subprocess.run(
                    ["top", "-l", "1", "-n", "5"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                results["checks"]["cpu"] = {
                    "status": "HEALTHY",
                    "output": cpu_result.stdout[:500]  # Truncate for readability
                }
            except Exception as e:
                results["checks"]["cpu"] = {"status": "ERROR", "error": str(e)}
                results["errors"].append(f"CPU check failed: {e}")

        # Check network connectivity
        if inputs.include_network:
            try:
                # Ping DNS servers to check network
                ping_result = subprocess.run(
                    ["ping", "-c", "3", "8.8.8.8"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                results["checks"]["network"] = {
                    "status": "HEALTHY" if ping_result.returncode == 0 else "ERROR",
                    "output": ping_result.stdout
                }
                if ping_result.returncode != 0:
                    results["errors"].append("Network connectivity issue: Cannot reach 8.8.8.8")
            except Exception as e:
                results["checks"]["network"] = {"status": "ERROR", "error": str(e)}
                results["errors"].append(f"Network check failed: {e}")

        # Determine overall status
        if results["errors"]:
            results["overall_status"] = "DEGRADED"
        elif results["warnings"]:
            results["overall_status"] = "WARNING"

        return {
            "success": True,
            "results": results,
            "message": f"System health check completed. Status: {results['overall_status']}"
        }

    except Exception as e:
        logger.error(f"System health check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"System health check failed: {e}"
        }


# ============================================================================
# Service Health Check Tools (Layer 3: Integration)
# ============================================================================

class CheckServiceHealthInput(UfInput):
    """Input for service health endpoint check."""
    service_url: str = Field(..., description="URL of the service to check (e.g., http://localhost:8080/health)")
    timeout: int = Field(default=10, description="Timeout in seconds")

    @field_validator('service_url')
    @classmethod
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError("service_url cannot be empty")
        return v.strip()

@uf(name="check_service_health", version="1.0.0",
   description="Check health endpoint of a service. Use for Layer 3 (Integration) troubleshooting to verify if a service is responding.")
def check_service_health(inputs: CheckServiceHealthInput) -> dict:
    """Check service health endpoint."""
    try:
        import urllib.request
        import urllib.error

        start_time = datetime.now()

        try:
            req = urllib.request.Request(inputs.service_url, headers={'User-Agent': 'OATS-Health-Check/1.0'})
            with urllib.request.urlopen(req, timeout=inputs.timeout) as response:
                response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                body = response.read().decode('utf-8')

                return {
                    "success": True,
                    "status_code": response.status,
                    "response_time_ms": response_time_ms,
                    "body": body[:500],  # Truncate for readability
                    "headers": dict(response.headers),
                    "message": f"Service healthy. Status: {response.status}, Response time: {response_time_ms}ms"
                }
        except urllib.error.HTTPError as e:
            response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return {
                "success": False,
                "status_code": e.code,
                "response_time_ms": response_time_ms,
                "error": str(e),
                "message": f"Service returned HTTP {e.code}: {e.reason}"
            }
        except urllib.error.URLError as e:
            return {
                "success": False,
                "status_code": None,
                "error": str(e),
                "message": f"Cannot reach service: {e.reason}"
            }

    except Exception as e:
        logger.error(f"Service health check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Health check failed: {e}"
        }


# ============================================================================
# Timeline and Change Detection Tools
# ============================================================================

class CheckRecentChangesInput(UfInput):
    """Input for checking recent changes."""
    time_window_hours: int = Field(default=24, description="How many hours back to check for changes")
    include_git: bool = Field(default=True, description="Include git history")
    include_system: bool = Field(default=True, description="Include system changes")

@uf(name="check_recent_changes", version="1.0.0",
   description="Check for recent changes in the system (code, config, deployments). Critical for Phase 3 (CORRELATE) of RCA.")
def check_recent_changes(inputs: CheckRecentChangesInput) -> dict:
    """Check for recent changes that might correlate with failures."""
    try:
        changes = {
            "timestamp": datetime.now().isoformat(),
            "time_window_hours": inputs.time_window_hours,
            "changes": []
        }

        # Check git history
        if inputs.include_git:
            try:
                git_result = subprocess.run(
                    ["git", "log", f"--since={inputs.time_window_hours} hours ago", "--oneline"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if git_result.returncode == 0 and git_result.stdout.strip():
                    changes["changes"].append({
                        "type": "git_commits",
                        "count": len(git_result.stdout.strip().split('\n')),
                        "details": git_result.stdout
                    })
            except Exception as e:
                logger.warning(f"Could not check git history: {e}")

        # Check for recently modified files
        if inputs.include_system:
            try:
                # Find recently modified files (excluding .git)
                find_result = subprocess.run(
                    ["find", ".", "-type", "f", "-mtime", f"-{max(1, inputs.time_window_hours // 24)}",
                     "-not", "-path", "*/.git/*", "-not", "-path", "*/venv/*", "-not", "-path", "*/__pycache__/*"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if find_result.returncode == 0:
                    modified_files = [f for f in find_result.stdout.strip().split('\n') if f]
                    if modified_files:
                        changes["changes"].append({
                            "type": "modified_files",
                            "count": len(modified_files),
                            "details": '\n'.join(modified_files[:20])  # Limit to 20 files
                        })
            except Exception as e:
                logger.warning(f"Could not check modified files: {e}")

        return {
            "success": True,
            "changes": changes,
            "message": f"Found {len(changes['changes'])} types of changes in last {inputs.time_window_hours} hours"
        }

    except Exception as e:
        logger.error(f"Recent changes check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Change detection failed: {e}"
        }


# ============================================================================
# Log Analysis Tools
# ============================================================================

class AnalyzeLogsInput(UfInput):
    """Input for log analysis."""
    log_file: str = Field(..., description="Path to log file")
    pattern: str = Field(default="error|exception|fail|timeout", description="Pattern to search for (regex)")
    time_window_minutes: Optional[int] = Field(None, description="Only analyze logs from last N minutes")
    max_lines: int = Field(default=100, description="Maximum lines to return")

    @field_validator('log_file')
    @classmethod
    def validate_log_file(cls, v):
        if not v or not v.strip():
            raise ValueError("log_file cannot be empty")
        return v.strip()

@uf(name="analyze_logs", version="1.0.0",
   description="Analyze log files for errors and patterns. Use in Phase 5 (ISOLATE) to find evidence of failures.")
def analyze_logs(inputs: AnalyzeLogsInput) -> dict:
    """Analyze log files for patterns and errors."""
    try:
        from core.workspace_security import validate_workspace_path

        # Validate path is within workspace
        log_path = validate_workspace_path(inputs.log_file, "log analysis")

        if not os.path.exists(log_path):
            return {
                "success": False,
                "error": "File not found",
                "message": f"Log file not found: {log_path}"
            }

        # Use grep to search for pattern
        grep_cmd = ["grep", "-E", "-i", inputs.pattern, str(log_path)]

        # If time window specified, use more complex filtering
        if inputs.time_window_minutes:
            # This is simplified - in production you'd parse timestamps
            grep_cmd = ["tail", "-n", str(inputs.max_lines * 10), str(log_path)]

        grep_result = subprocess.run(
            grep_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        matches = grep_result.stdout.strip().split('\n') if grep_result.stdout.strip() else []
        matches = [m for m in matches if m][:inputs.max_lines]

        return {
            "success": True,
            "log_file": inputs.log_file,
            "pattern": inputs.pattern,
            "match_count": len(matches),
            "matches": matches,
            "message": f"Found {len(matches)} matches in {inputs.log_file}"
        }

    except Exception as e:
        logger.error(f"Log analysis failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Log analysis failed: {e}"
        }


# ============================================================================
# Dependency Tracing Tools (Layer 3)
# ============================================================================

class CheckDependencyInput(UfInput):
    """Input for dependency health check."""
    dependency_host: str = Field(..., description="Hostname or IP of dependency")
    dependency_port: int = Field(..., description="Port number")
    protocol: str = Field(default="tcp", description="Protocol to check (tcp, http)")

    @field_validator('dependency_host')
    @classmethod
    def validate_host(cls, v):
        if not v or not v.strip():
            raise ValueError("dependency_host cannot be empty")
        return v.strip()

@uf(name="check_dependency", version="1.0.0",
   description="Check if a dependency (database, cache, API) is reachable. Use for Layer 3 (Integration) dependency tracing.")
def check_dependency(inputs: CheckDependencyInput) -> dict:
    """Check dependency connectivity."""
    try:
        start_time = datetime.now()

        if inputs.protocol.lower() == "http":
            # Use service health check for HTTP
            return check_service_health(CheckServiceHealthInput(
                service_url=f"http://{inputs.dependency_host}:{inputs.dependency_port}/health"
            ))
        else:
            # Use netcat for TCP check
            nc_result = subprocess.run(
                ["nc", "-zv", inputs.dependency_host, str(inputs.dependency_port)],
                capture_output=True,
                text=True,
                timeout=10
            )

            response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return {
                "success": nc_result.returncode == 0,
                "host": inputs.dependency_host,
                "port": inputs.dependency_port,
                "response_time_ms": response_time_ms,
                "output": nc_result.stderr,  # nc outputs to stderr
                "message": f"Dependency {'reachable' if nc_result.returncode == 0 else 'unreachable'}: {inputs.dependency_host}:{inputs.dependency_port}"
            }

    except Exception as e:
        logger.error(f"Dependency check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Dependency check failed: {e}"
        }


# ============================================================================
# Finish Tool for RCA Completion
# ============================================================================

class FinishInput(UfInput):
    """Input for finish action."""
    reason: str = Field(..., description="Reason for completion with summary of findings")
    root_cause: Optional[str] = Field(None, description="Identified root cause")
    fix_applied: Optional[str] = Field(None, description="Fix that was applied")

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v):
        if not v or not v.strip():
            raise ValueError("reason cannot be empty")
        return v.strip()

@uf(name="finish", version="1.0.0",
   description="Mark goal as complete. MUST include reason summarizing findings, root cause, and fix (if applied).")
def finish(inputs: FinishInput) -> dict:
    """Complete the goal and return summary."""
    summary_parts = [inputs.reason]

    if inputs.root_cause:
        summary_parts.append(f"\n\nRoot Cause: {inputs.root_cause}")

    if inputs.fix_applied:
        summary_parts.append(f"\nFix Applied: {inputs.fix_applied}")

    summary = '\n'.join(summary_parts)

    return {
        "success": True,
        "completed": True,
        "reason": inputs.reason,
        "root_cause": inputs.root_cause,
        "fix_applied": inputs.fix_applied,
        "message": summary
    }
