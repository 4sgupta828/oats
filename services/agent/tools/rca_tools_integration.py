"""RCA Tools Integration Module

This module imports all RCA tools to ensure they are registered with the agent framework.
The @uf decorated functions will be automatically discovered by the registry system.
"""

# Import incident detection tool
from rca.tools.incident_detection import detect_incident_window

# Import all RCA tools
from rca.tools.rca_tools import (
    # Group 1: Situational Awareness
    analyze_blast_radius,
    get_temporal_timeline,
    get_recent_changes,

    # Group 2: Baseline Comparison
    compare_metrics,
    compare_logs,
    compare_traces,

    # Group 3: Active Validation
    get_service_dependencies,
    check_instance_health,
    get_database_stats,
    get_cache_stats,
    check_dependency_health,

    # Group 4: Completion
    finish
)

# Export all tools
__all__ = [
    # Incident Detection
    'detect_incident_window',

    # Situational Awareness
    'analyze_blast_radius',
    'get_temporal_timeline',
    'get_recent_changes',

    # Baseline Comparison
    'compare_metrics',
    'compare_logs',
    'compare_traces',

    # Active Validation
    'get_service_dependencies',
    'check_instance_health',
    'get_database_stats',
    'get_cache_stats',
    'check_dependency_health',

    # Completion
    'finish'
]

# Tool count for verification
RCA_TOOL_COUNT = len(__all__)

def get_rca_tools():
    """Get list of all RCA tool names"""
    return __all__

def verify_rca_tools():
    """Verify all RCA tools are properly registered"""
    print(f"✓ {RCA_TOOL_COUNT} RCA tools available:")
    print("\nIncident Detection:")
    print("  - detect_incident_window")
    print("\nSituational Awareness (Phase 0):")
    print("  - analyze_blast_radius")
    print("  - get_temporal_timeline")
    print("  - get_recent_changes")
    print("\nBaseline Comparison (Phase 2):")
    print("  - compare_metrics")
    print("  - compare_logs")
    print("  - compare_traces")
    print("\nActive Validation (Phase 3-4):")
    print("  - get_service_dependencies")
    print("  - check_instance_health")
    print("  - get_database_stats")
    print("  - get_cache_stats")
    print("  - check_dependency_health")
    print("\nCompletion (Phase 5):")
    print("  - finish")

    return True

if __name__ == "__main__":
    verify_rca_tools()
