#!/usr/bin/env python3
"""
Run incident detection tool on a dataset with comprehensive output for RCA.

Usage:
    python run_incident_detection.py <data_dir>

Example:
    python run_incident_detection.py ~/oats/output/data_20251030_124211
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add the services/agent directory to the path
sys.path.insert(0, str(Path(__file__).parent / "services" / "agent"))

from rca.tools.incident_detection import detect_incident_window, DetectIncidentWindowInput


def format_timestamp(ts: float) -> str:
    """Format timestamp as readable datetime"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f}m ({seconds:.1f}s)"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}h ({seconds:.1f}s)"


def build_comprehensive_report(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build comprehensive structured report for RCA tool"""

    if not result.get("incident_detected"):
        return {
            "status": "no_incident",
            "message": result.get("message", "No incident detected"),
            "data_window": result.get("data_time_range", {})
        }

    data_range = result.get("detection_metadata", {}).get("data_time_range", {})
    baseline = result.get("baseline_window", {})
    incident = result.get("incident_window", {})
    anomalies = result.get("anomalies", [])
    primary = result.get("primary_symptom", {})
    causal_rels = result.get("causal_relationships", [])

    # Build anomaly lookup by cluster_id
    anomaly_map = {a["cluster_id"]: a for a in anomalies}

    # Categorize anomalies by relationship
    primary_anomalies = [a for a in anomalies if a["relationship"] == "PRIMARY"]
    cascading_anomalies = [a for a in anomalies if a["relationship"] == "CASCADING"]
    correlated_anomalies = [a for a in anomalies if a["relationship"] == "CORRELATED"]
    secondary_symptoms = [a for a in anomalies if a["relationship"] == "SECONDARY_SYMPTOM"]

    # Build timeline: chronological order of all anomaly starts
    timeline = []
    for anomaly in sorted(anomalies, key=lambda x: x["start_time"]):
        timeline.append({
            "cluster_id": anomaly["cluster_id"],
            "timestamp": anomaly["start_time"],
            "timestamp_formatted": format_timestamp(anomaly["start_time"]),
            "event_type": "anomaly_start",
            "component": anomaly["component"],
            "metric": anomaly["metric"],
            "direction": anomaly["direction"],
            "pattern": anomaly["pattern"],
            "severity": anomaly["severity"],
            "relationship": anomaly["relationship"],
            "peak_z_score": anomaly["peak_z_score"],
            "confidence": anomaly["confidence"],
            "detection_methods": anomaly["detection_methods"]
        })

        # Add end event if anomaly has resolved
        if anomaly["end_time"]:
            timeline.append({
                "cluster_id": anomaly["cluster_id"],
                "timestamp": anomaly["end_time"],
                "timestamp_formatted": format_timestamp(anomaly["end_time"]),
                "event_type": "anomaly_end",
                "component": anomaly["component"],
                "metric": anomaly["metric"],
                "duration": anomaly["duration"]
            })

    # Sort timeline chronologically
    timeline.sort(key=lambda x: x["timestamp"])

    # Build causal graph with full details
    causal_graph = []
    for rel in causal_rels:
        cause = anomaly_map.get(rel["cause_cluster_id"])
        effect = anomaly_map.get(rel["effect_cluster_id"])

        if cause and effect:
            causal_graph.append({
                "cause_cluster_id": rel["cause_cluster_id"],
                "effect_cluster_id": rel["effect_cluster_id"],
                "granger_p_value": rel["granger_p_value"],
                "confidence": rel["confidence"],
                "lag_buckets": rel["lag"],
                "cause_details": {
                    "component": cause["component"],
                    "metric": cause["metric"],
                    "direction": cause["direction"],
                    "start_time": cause["start_time"],
                    "start_time_formatted": format_timestamp(cause["start_time"])
                },
                "effect_details": {
                    "component": effect["component"],
                    "metric": effect["metric"],
                    "direction": effect["direction"],
                    "start_time": effect["start_time"],
                    "start_time_formatted": format_timestamp(effect["start_time"])
                },
                "interpretation": f"{cause['component']}.{cause['metric']} ({cause['direction']}) → {effect['component']}.{effect['metric']} ({effect['direction']})"
            })

    # Build correlation groups (anomalies that started around the same time)
    correlation_groups = []
    time_threshold = 10  # seconds
    processed = set()

    for i, a1 in enumerate(anomalies):
        if a1["cluster_id"] in processed:
            continue

        group = [a1]
        processed.add(a1["cluster_id"])

        for a2 in anomalies[i+1:]:
            if a2["cluster_id"] in processed:
                continue

            time_diff = abs(a2["start_time"] - a1["start_time"])
            if time_diff <= time_threshold:
                group.append(a2)
                processed.add(a2["cluster_id"])

        if len(group) > 1:
            correlation_groups.append({
                "group_start_time": min(a["start_time"] for a in group),
                "group_start_time_formatted": format_timestamp(min(a["start_time"] for a in group)),
                "time_window": time_threshold,
                "cluster_count": len(group),
                "clusters": [
                    {
                        "cluster_id": a["cluster_id"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "direction": a["direction"],
                        "severity": a["severity"],
                        "relationship": a["relationship"]
                    }
                    for a in sorted(group, key=lambda x: x["start_time"])
                ]
            })

    # Build comprehensive report
    report = {
        "summary": {
            "status": "incident_detected",
            "analyzer_version": result.get("analyzer_version", "v3"),
            "v3_features_enabled": result.get("v3_features_enabled", {}),
            "total_anomaly_clusters": len(anomalies),
            "affected_components": result.get("affected_components", []),
            "affected_component_count": len(result.get("affected_components", [])),
            "causal_relationships_found": len(causal_rels),
            "correlation_groups_found": len(correlation_groups)
        },

        "time_windows": {
            "total_data_window": {
                "start_time": data_range.get("start"),
                "end_time": data_range.get("end"),
                "start_time_formatted": format_timestamp(data_range.get("start", 0)) if data_range.get("start") else None,
                "end_time_formatted": format_timestamp(data_range.get("end", 0)) if data_range.get("end") else None,
                "duration_seconds": data_range.get("end", 0) - data_range.get("start", 0) if data_range.get("end") and data_range.get("start") else 0,
                "duration_formatted": format_duration(data_range.get("end", 0) - data_range.get("start", 0)) if data_range.get("end") and data_range.get("start") else "0s"
            },

            "baseline_windows": [
                {
                    "window_id": 1,
                    "start_time": baseline.get("start_time"),
                    "end_time": baseline.get("end_time"),
                    "start_time_formatted": format_timestamp(baseline.get("start_time", 0)),
                    "end_time_formatted": format_timestamp(baseline.get("end_time", 0)),
                    "duration_seconds": baseline.get("duration", 0),
                    "duration_formatted": format_duration(baseline.get("duration", 0)),
                    "quality": baseline.get("quality"),
                    "stability_score": baseline.get("stability_score", 0),
                    "samples": baseline.get("samples", 0),
                    "detection_method": baseline.get("detection_method", "unknown")
                }
            ],

            "incident_windows": [
                {
                    "window_id": 1,
                    "start_time": incident.get("start_time"),
                    "end_time": incident.get("end_time"),
                    "start_time_formatted": format_timestamp(incident.get("start_time", 0)),
                    "end_time_formatted": format_timestamp(incident.get("end_time", 0)) if incident.get("end_time") else "ONGOING",
                    "duration_seconds": incident.get("duration", 0),
                    "duration_formatted": format_duration(incident.get("duration", 0)),
                    "status": incident.get("status"),
                    "anomaly_cluster_count": len(anomalies)
                }
            ]
        },

        "primary_symptom": {
            "cluster_id": next((a["cluster_id"] for a in primary_anomalies), None),
            "component": primary.get("component"),
            "metric": primary.get("metric"),
            "pattern": primary.get("pattern"),
            "direction": primary.get("direction"),
            "severity": primary.get("severity"),
            "z_score": primary.get("z_score"),
            "start_time": primary.get("start_time"),
            "start_time_formatted": format_timestamp(primary.get("start_time", 0)),
            "description": primary.get("description"),
            "full_details": primary_anomalies[0] if primary_anomalies else None
        },

        "anomaly_clusters": {
            "all_clusters": [
                {
                    "cluster_id": a["cluster_id"],
                    "component": a["component"],
                    "metric": a["metric"],
                    "start_time": a["start_time"],
                    "end_time": a["end_time"],
                    "start_time_formatted": format_timestamp(a["start_time"]),
                    "end_time_formatted": format_timestamp(a["end_time"]) if a["end_time"] else "ONGOING",
                    "duration_seconds": a["duration"],
                    "duration_formatted": format_duration(a["duration"]),
                    "peak_time": a["peak_time"],
                    "peak_time_formatted": format_timestamp(a["peak_time"]),
                    "peak_z_score": a["peak_z_score"],
                    "direction": a["direction"],
                    "pattern": a["pattern"],
                    "severity": a["severity"],
                    "relationship": a["relationship"],
                    "confidence": a["confidence"],
                    "detection_methods": a["detection_methods"],
                    "anomaly_point_count": a["anomaly_count"]
                }
                for a in sorted(anomalies, key=lambda x: x["start_time"])
            ],

            "by_relationship": {
                "PRIMARY": [
                    {
                        "cluster_id": a["cluster_id"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "direction": a["direction"],
                        "pattern": a["pattern"],
                        "severity": a["severity"],
                        "start_time": a["start_time"],
                        "start_time_formatted": format_timestamp(a["start_time"]),
                        "z_score": a["peak_z_score"]
                    }
                    for a in primary_anomalies
                ],

                "CASCADING": [
                    {
                        "cluster_id": a["cluster_id"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "direction": a["direction"],
                        "pattern": a["pattern"],
                        "severity": a["severity"],
                        "start_time": a["start_time"],
                        "start_time_formatted": format_timestamp(a["start_time"]),
                        "delay_from_primary_seconds": a["start_time"] - primary.get("start_time", 0) if primary.get("start_time") else 0
                    }
                    for a in sorted(cascading_anomalies, key=lambda x: x["start_time"])
                ],

                "CORRELATED": [
                    {
                        "cluster_id": a["cluster_id"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "direction": a["direction"],
                        "pattern": a["pattern"],
                        "severity": a["severity"],
                        "start_time": a["start_time"],
                        "start_time_formatted": format_timestamp(a["start_time"]),
                        "time_diff_from_primary_seconds": a["start_time"] - primary.get("start_time", 0) if primary.get("start_time") else 0
                    }
                    for a in sorted(correlated_anomalies, key=lambda x: x["start_time"])
                ],

                "SECONDARY_SYMPTOM": [
                    {
                        "cluster_id": a["cluster_id"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "direction": a["direction"],
                        "pattern": a["pattern"],
                        "severity": a["severity"],
                        "start_time": a["start_time"],
                        "start_time_formatted": format_timestamp(a["start_time"]),
                        "delay_from_primary_seconds": a["start_time"] - primary.get("start_time", 0) if primary.get("start_time") else 0
                    }
                    for a in sorted(secondary_symptoms, key=lambda x: x["start_time"])
                ]
            },

            "by_component": {}
        },

        "timeline": timeline,

        "relationships": {
            "causal_relationships": causal_graph,
            "correlation_groups": correlation_groups,
            "cascading_chain": [
                {
                    "cluster_id": a["cluster_id"],
                    "component": a["component"],
                    "metric": a["metric"],
                    "direction": a["direction"],
                    "start_time": a["start_time"],
                    "start_time_formatted": format_timestamp(a["start_time"]),
                    "delay_from_primary_seconds": a["start_time"] - primary.get("start_time", 0) if primary.get("start_time") else 0
                }
                for a in sorted(cascading_anomalies, key=lambda x: x["start_time"])
            ]
        },

        "detection_metadata": result.get("detection_metadata", {})
    }

    # Group anomalies by component
    by_component = {}
    for a in anomalies:
        comp = a["component"]
        if comp not in by_component:
            by_component[comp] = []
        by_component[comp].append({
            "cluster_id": a["cluster_id"],
            "metric": a["metric"],
            "direction": a["direction"],
            "pattern": a["pattern"],
            "severity": a["severity"],
            "start_time": a["start_time"],
            "start_time_formatted": format_timestamp(a["start_time"]),
            "relationship": a["relationship"]
        })

    report["anomaly_clusters"]["by_component"] = by_component

    return report


def print_comprehensive_report(report: Dict[str, Any]):
    """Print human-readable comprehensive report"""

    print("\n" + "=" * 100)
    print("COMPREHENSIVE INCIDENT DETECTION REPORT FOR RCA")
    print("=" * 100)

    summary = report["summary"]
    windows = report["time_windows"]
    primary = report["primary_symptom"]
    clusters = report["anomaly_clusters"]
    timeline = report["timeline"]
    relationships = report["relationships"]

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Status: {summary['status']}")
    print(f"Analyzer Version: {summary['analyzer_version']}")
    print(f"Total Anomaly Clusters: {summary['total_anomaly_clusters']}")
    print(f"Affected Components: {summary['affected_component_count']}")
    print(f"Causal Relationships: {summary['causal_relationships_found']}")
    print(f"Correlation Groups: {summary['correlation_groups_found']}")

    v3_features = summary.get('v3_features_enabled', {})
    print("\nV3 Features Enabled:")
    for feature, enabled in v3_features.items():
        status = "✓" if enabled else "✗"
        print(f"  {status} {feature}")

    # Time Windows
    print("\n" + "=" * 100)
    print("TIME WINDOWS")
    print("=" * 100)

    total_window = windows["total_data_window"]
    print(f"\nTotal Data Window:")
    print(f"  Start:    {total_window['start_time_formatted']} (ts: {total_window['start_time']})")
    print(f"  End:      {total_window['end_time_formatted']} (ts: {total_window['end_time']})")
    print(f"  Duration: {total_window['duration_formatted']}")

    print(f"\nBaseline Windows ({len(windows['baseline_windows'])}):")
    for bw in windows["baseline_windows"]:
        print(f"  Window #{bw['window_id']}:")
        print(f"    Start:    {bw['start_time_formatted']} (ts: {bw['start_time']})")
        print(f"    End:      {bw['end_time_formatted']} (ts: {bw['end_time']})")
        print(f"    Duration: {bw['duration_formatted']}")
        print(f"    Quality:  {bw['quality']} (stability: {bw['stability_score']:.2f})")
        print(f"    Samples:  {bw['samples']}")
        print(f"    Method:   {bw['detection_method']}")

    print(f"\nIncident Windows ({len(windows['incident_windows'])}):")
    for iw in windows["incident_windows"]:
        print(f"  Window #{iw['window_id']}:")
        print(f"    Start:    {iw['start_time_formatted']} (ts: {iw['start_time']})")
        print(f"    End:      {iw['end_time_formatted']}" + (f" (ts: {iw['end_time']})" if iw['end_time'] else ""))
        print(f"    Duration: {iw['duration_formatted']}")
        print(f"    Status:   {iw['status']}")
        print(f"    Anomalies: {iw['anomaly_cluster_count']} clusters")

    # Primary Symptom
    print("\n" + "=" * 100)
    print("PRIMARY SYMPTOM")
    print("=" * 100)
    print(f"Cluster ID: {primary['cluster_id']}")
    print(f"Component:  {primary['component']}")
    print(f"Metric:     {primary['metric']}")
    print(f"Direction:  {primary['direction']}")
    print(f"Pattern:    {primary['pattern']}")
    print(f"Severity:   {primary['severity']}")
    print(f"Z-Score:    {primary['z_score']:.2f}")
    print(f"Start Time: {primary['start_time_formatted']} (ts: {primary['start_time']})")
    print(f"Description: {primary['description']}")

    # Timeline
    print("\n" + "=" * 100)
    print("CHRONOLOGICAL TIMELINE OF ALL ANOMALIES")
    print("=" * 100)
    print(f"\nTotal events in timeline: {len(timeline)}")
    print("\nTimeline:")
    for i, event in enumerate(timeline, 1):
        if event["event_type"] == "anomaly_start":
            print(f"\n  [{i}] {event['timestamp_formatted']} (ts: {event['timestamp']:.2f})")
            print(f"      EVENT: Anomaly START")
            print(f"      Cluster: {event['cluster_id']}")
            print(f"      Component: {event['component']}")
            print(f"      Metric: {event['metric']}")
            print(f"      Direction: {event['direction']} | Pattern: {event['pattern']}")
            print(f"      Severity: {event['severity']} | Relationship: {event['relationship']}")
            print(f"      Z-Score: {event['peak_z_score']:.2f} | Confidence: {event['confidence']:.2f}")
            print(f"      Detection: {', '.join(event['detection_methods'])}")
        else:
            print(f"\n  [{i}] {event['timestamp_formatted']} (ts: {event['timestamp']:.2f})")
            print(f"      EVENT: Anomaly END")
            print(f"      Cluster: {event['cluster_id']}")
            print(f"      Duration: {format_duration(event['duration'])}")

    # Anomaly Clusters by Relationship
    print("\n" + "=" * 100)
    print("ANOMALY CLUSTERS BY RELATIONSHIP TYPE")
    print("=" * 100)

    by_rel = clusters["by_relationship"]

    if by_rel["PRIMARY"]:
        print(f"\nPRIMARY Anomalies ({len(by_rel['PRIMARY'])}):")
        for a in by_rel["PRIMARY"]:
            print(f"  • Cluster {a['cluster_id']}: {a['component']}.{a['metric']}")
            print(f"    {a['direction']} | {a['pattern']} | Severity: {a['severity']}")
            print(f"    Start: {a['start_time_formatted']} | Z-Score: {a['z_score']:.2f}")

    if by_rel["CASCADING"]:
        print(f"\nCASCADING Anomalies ({len(by_rel['CASCADING'])}):")
        for a in by_rel["CASCADING"]:
            print(f"  • Cluster {a['cluster_id']}: {a['component']}.{a['metric']}")
            print(f"    {a['direction']} | {a['pattern']} | Severity: {a['severity']}")
            print(f"    Start: {a['start_time_formatted']} | Delay from primary: {format_duration(a['delay_from_primary_seconds'])}")

    if by_rel["CORRELATED"]:
        print(f"\nCORRELATED Anomalies ({len(by_rel['CORRELATED'])}):")
        for a in by_rel["CORRELATED"]:
            print(f"  • Cluster {a['cluster_id']}: {a['component']}.{a['metric']}")
            print(f"    {a['direction']} | {a['pattern']} | Severity: {a['severity']}")
            print(f"    Start: {a['start_time_formatted']} | Time diff from primary: {a['time_diff_from_primary_seconds']:.1f}s")

    if by_rel["SECONDARY_SYMPTOM"]:
        print(f"\nSECONDARY SYMPTOMS ({len(by_rel['SECONDARY_SYMPTOM'])}):")
        for a in by_rel["SECONDARY_SYMPTOM"]:
            print(f"  • Cluster {a['cluster_id']}: {a['component']}.{a['metric']}")
            print(f"    {a['direction']} | {a['pattern']} | Severity: {a['severity']}")
            print(f"    Start: {a['start_time_formatted']} | Delay from primary: {format_duration(a['delay_from_primary_seconds'])}")

    # Relationships
    print("\n" + "=" * 100)
    print("CAUSAL RELATIONSHIPS (Granger Causality)")
    print("=" * 100)
    causal = relationships["causal_relationships"]
    if causal:
        print(f"\nFound {len(causal)} causal relationships:")
        for i, rel in enumerate(causal, 1):
            print(f"\n  [{i}] {rel['interpretation']}")
            print(f"      Confidence: {rel['confidence']:.2%} | P-value: {rel['granger_p_value']:.4f} | Lag: {rel['lag_buckets']} buckets")
            print(f"      Cause:  Cluster {rel['cause_cluster_id']} at {rel['cause_details']['start_time_formatted']}")
            print(f"      Effect: Cluster {rel['effect_cluster_id']} at {rel['effect_details']['start_time_formatted']}")
    else:
        print("\nNo causal relationships detected.")

    print("\n" + "=" * 100)
    print("CORRELATION GROUPS (co-occurring anomalies)")
    print("=" * 100)
    corr_groups = relationships["correlation_groups"]
    if corr_groups:
        print(f"\nFound {len(corr_groups)} correlation groups:")
        for i, group in enumerate(corr_groups, 1):
            print(f"\n  Group {i}: {group['cluster_count']} clusters starting around {group['group_start_time_formatted']}")
            for cluster in group["clusters"]:
                print(f"    • Cluster {cluster['cluster_id']}: {cluster['component']}.{cluster['metric']}")
                print(f"      {cluster['direction']} | {cluster['severity']} | {cluster['relationship']}")
    else:
        print("\nNo correlation groups found (all anomalies are temporally separated).")

    # Anomalies by Component
    print("\n" + "=" * 100)
    print("ANOMALIES GROUPED BY COMPONENT")
    print("=" * 100)
    by_comp = clusters["by_component"]
    for comp, comp_anomalies in sorted(by_comp.items()):
        print(f"\n{comp} ({len(comp_anomalies)} anomalies):")
        for a in sorted(comp_anomalies, key=lambda x: x["start_time"]):
            print(f"  • Cluster {a['cluster_id']}: {a['metric']}")
            print(f"    {a['direction']} | {a['pattern']} | {a['severity']} | {a['relationship']}")
            print(f"    Start: {a['start_time_formatted']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_incident_detection.py <data_dir>")
        print("Example: python run_incident_detection.py ~/oats/output/data_20251030_124211")
        sys.exit(1)

    data_dir = os.path.expanduser(sys.argv[1])

    if not os.path.exists(data_dir):
        print(f"Error: Data directory does not exist: {data_dir}")
        sys.exit(1)

    print(f"Running incident detection on: {data_dir}")
    print("=" * 100)

    # Create input with all V3 features enabled (defaults)
    inputs = DetectIncidentWindowInput(
        data_dir=data_dir,
        sensitivity="medium",
        enable_bayesian_changepoint=True,
        enable_multivariate=True,
        enable_causality=True,
        enable_seasonality=True,
        enable_streaming=False
    )

    print("\nConfiguration:")
    print(f"  Sensitivity: {inputs.sensitivity}")
    print(f"  Bayesian Changepoint: {inputs.enable_bayesian_changepoint}")
    print(f"  Multivariate Detection: {inputs.enable_multivariate}")
    print(f"  Causality Analysis: {inputs.enable_causality}")
    print(f"  Seasonality Detection: {inputs.enable_seasonality}")
    print(f"  Streaming: {inputs.enable_streaming}")

    print("\nRunning detection...")
    result = detect_incident_window(inputs)

    # Build comprehensive report
    report = build_comprehensive_report(result)

    # Save raw result
    raw_output_file = os.path.join(data_dir, "incident_detection_raw.json")
    with open(raw_output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nRaw result saved to: {raw_output_file}")

    # Save comprehensive report
    report_output_file = os.path.join(data_dir, "incident_detection_report.json")
    with open(report_output_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Comprehensive report saved to: {report_output_file}")

    # Print comprehensive report
    print_comprehensive_report(report)

    print("\n" + "=" * 100)
    print("END OF REPORT")
    print("=" * 100)
    print(f"\nFiles saved:")
    print(f"  1. Raw detection output: {raw_output_file}")
    print(f"  2. Comprehensive RCA report: {report_output_file}")


if __name__ == "__main__":
    main()
