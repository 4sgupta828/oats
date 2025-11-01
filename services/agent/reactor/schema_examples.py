# reactor/schema_examples.py
"""
Auto-generate JSON examples from Pydantic models for prompts.
This eliminates the need to manually sync schema examples in prompts.
"""

import json
from typing import Dict
from reactor.models import (
    Fact, TimelineEvent, Context, Symptom, CausalLink,
    CompetingHypothesis, Diagnosis, Task, ActiveTask,
    Hypothesis, ReflectSection, StrategizeSection, State, ActSection,
    DiagnosticMetadata, FailureMetadata
)


def generate_schema_examples() -> Dict[str, str]:
    """
    Generate JSON examples from Pydantic models for use in prompts.

    This ensures that prompt examples ALWAYS match the current model schema,
    eliminating schema drift and validation errors.

    Returns:
        Dictionary mapping example names to formatted JSON strings
    """

    # Fact example
    fact_example = Fact(
        id=1,
        desc="p99 latency increased from 150ms to 2.5s starting at 10:15 AM (z=12.3, p<0.001)",
        turn=3,
        layer="RUNTIME"
    )

    # TimelineEvent example
    timeline_example = TimelineEvent(
        timestamp="T-3min (2025-10-31 10:12:00)",
        event="Deployed user-cache v1.2.3 with modified TTL configuration",
        relevance="HIGH",
        factIDs=[2, 3]
    )

    # Context example
    context_example = Context(
        architecture="api-service is a REST API handling 10k req/s; caches user profiles via user-cache (Redis); returns user data to frontend",
        dependencies="Upstream: user-cache (Redis), postgres-db (primary store). Downstream: frontend-service, mobile-app. Isolation boundary: user-cache",
        temporal="Anomaly started at 10:15 AM UTC. user-cache v1.2.3 deployed at 10:12 AM (T-3min). No other deployments in 24h window.",
        environment="Production environment, 10 api-service instances behind ALB, auto-scaling 5-20 pods, us-east-1"
    )

    # Symptom example
    symptom_example = Symptom(
        description="API /users/:id endpoint returning 500 errors at 15% error rate",
        layer="INTEGRATION",
        scope="15% of requests (1.5k/min out of 10k/min)",
        started="2025-10-31T10:15:00Z"
    )

    # CausalLink example - showing proper object structure
    causal_link_example = CausalLink(
        level="proximate_cause",
        layer="INTEGRATION",
        description="user-cache v1.2.3 TTL bug caused 90% cache eviction → cache hit ratio collapsed from 98% to 25%",
        factIDs=[1, 2, 3]
    )

    # CompetingHypothesis example
    competing_hypothesis_example = CompetingHypothesis(
        id="H1",
        claim="user-cache v1.2.3 deployment introduced TTL configuration bug causing cache eviction",
        layer="INTEGRATION",
        prior_confidence=0.7,
        current_confidence=0.95,
        status="CONFIRMED",
        evidence_for=[
            "factID: 1 - Cache hit ratio dropped from 98% to 25% at T+0",
            "factID: 2 - user-cache v1.2.3 deployed at T-3min",
            "factID: 3 - Config diff shows TTL changed from 3600s to 60s"
        ],
        evidence_against=[]
    )

    # Diagnosis example with all components
    diagnosis_example = Diagnosis(
        symptom=symptom_example,
        context=context_example,
        timeline=[timeline_example],
        causalChain=[causal_link_example],
        layerStatus={
            "INFRASTRUCTURE": "HEALTHY",
            "RUNTIME": "HEALTHY",
            "INTEGRATION": "DEGRADED",
            "BUSINESS_LOGIC": "FAULTY"
        },
        competingHypotheses=[competing_hypothesis_example],
        rootCause="user-cache v1.2.3 TTL config bug (changed from 3600s to 60s) caused 90% cache eviction, leading to 20× DB query increase and API 500 errors"
    )

    # Task example
    # NOTE: Use alias "description" (not "desc") to match JSON schema
    task_example = Task(
        id=1,
        description="Identify root cause of API 500 errors in /users/:id endpoint",
        status="active"
    )

    # ActiveTask example
    active_task_example = ActiveTask(
        id=1,
        archetype="DIAGNOSE",
        phase="EVIDENCE_GATHERING",
        turns=5
    )

    # Hypothesis example
    hypothesis_example = Hypothesis(
        claim="Cache hit ratio dropped due to recent deployment",
        test="Compare cache metrics before/after deployment timestamp",
        signal="Metric comparison will show correlation between deployment and cache degradation"
    )

    # DiagnosticMetadata example
    diagnostic_metadata_example = DiagnosticMetadata(
        investigation_phase="EVIDENCE_GATHERING",
        layer_focus="INTEGRATION",
        signal_quality="STRONG",
        causality_level="PROXIMATE_CAUSE",
        confidence={
            "problem_definition": "HIGH",
            "root_cause_identified": "MEDIUM",
            "fix_will_work": "LOW"
        }
    )

    # FailureMetadata example
    failure_metadata_example = FailureMetadata(
        type="EXECUTION_FAILURE",
        category="tool_error",
        recovery_level="E2",
        recovery_plan="Retry with corrected tool parameters"
    )

    # ReflectSection example
    reflect_example = ReflectSection(
        turn=5,
        outcome="SUCCESS",
        hypothesisResult="CONFIRMED",
        insight="Cache hit ratio dropped from 98% to 25% immediately after user-cache v1.2.3 deployment, confirming deployment correlation",
        diagnostic=diagnostic_metadata_example
    )

    # StrategizeSection example
    strategize_example = StrategizeSection(
        reasoning="Need to inspect actual config changes in v1.2.3 to identify root cause of cache eviction",
        hypothesis=hypothesis_example,
        ifInvalidated="If config unchanged, investigate application code changes in user-cache v1.2.3"
    )

    # State example
    state_example = State(
        goal="Diagnose root cause of API /users/:id 500 errors",
        tasks=[task_example],
        active=active_task_example,
        facts=[fact_example],
        ruled_out=["Database connection pool exhaustion - DB metrics show healthy connection counts"],
        unknowns=["What specific config change in user-cache v1.2.3 caused cache eviction?"],
        diagnosis=diagnosis_example
    )

    # ActSection example
    act_example = ActSection(
        tool="compare_versions",
        params={
            "service": "user-cache",
            "version1": "v1.2.2",
            "version2": "v1.2.3",
            "focus": "config"
        },
        safe="Read-only comparison of configuration files"
    )

    # Create a complete ParsedLLMResponse example
    from reactor.models import ParsedLLMResponse

    complete_response = ParsedLLMResponse(
        reflect=reflect_example,
        strategize=strategize_example,
        state=state_example,
        act=act_example,
        is_finish=False,
        raw_response=""
    )

    # Create variant examples for different scenarios

    # Success path variant (for phase 4 - confirmed hypothesis, moving to synthesis)
    success_reflect = ReflectSection(
        turn=10,
        outcome="SUCCESS",
        hypothesisResult="CONFIRMED",
        insight="All dependencies of user-cache validated as healthy. Redis cluster latency normal, config service had no changes. user-cache confirmed as source.",
        diagnostic=DiagnosticMetadata(
            investigation_phase="CAUSAL_CONFIRMATION",
            layer_focus="BUSINESS_LOGIC",
            signal_quality="STRONG",
            causality_level="ROOT_CAUSE",
            confidence={
                "problem_definition": "HIGH",
                "root_cause_identified": "HIGH",
                "fix_will_work": "HIGH"
            }
        )
    )

    success_state = State(
        goal=state_example.goal,
        tasks=state_example.tasks,
        active=ActiveTask(id=2, archetype="DIAGNOSE", phase="SYNTHESIS", turns=1),
        facts=state_example.facts,
        ruled_out=state_example.ruled_out,
        unknowns=[],
        diagnosis=diagnosis_example
    )

    success_response = ParsedLLMResponse(
        reflect=success_reflect,
        strategize=StrategizeSection(
            reasoning="Phase 4 complete. All dependencies validated as healthy. Transitioning to Phase 5 to synthesize complete causal chain.",
            hypothesis=Hypothesis(
                claim="Complete RCA ready for synthesis",
                test="Build causal chain from root cause to symptom",
                signal="Comprehensive explanation with evidence"
            ),
            ifInvalidated="N/A - investigation complete"
        ),
        state=success_state,
        act=ActSection(
            tool="finish",
            params={
                "root_cause_component": "user-cache",
                "root_cause_finding": "user-cache v1.2.3 deployment introduced TTL calculation bug"
            }
        ),
        is_finish=True,
        raw_response=""
    )

    # Pivot path variant (for phase 4 - hypothesis invalidated, pivoting to new layer)
    pivot_reflect = ReflectSection(
        turn=10,
        outcome="SUCCESS",
        hypothesisResult="INVALIDATED",
        insight="Discovered storage-volume-xyz has disk IO wait time of 800ms (baseline: 5ms). database-1 is a victim, not the source. Pivoting investigation.",
        diagnostic=DiagnosticMetadata(
            investigation_phase="CAUSAL_CONFIRMATION",
            layer_focus="INFRASTRUCTURE",
            signal_quality="STRONG",
            causality_level="PROXIMATE_CAUSE",
            confidence={
                "problem_definition": "HIGH",
                "root_cause_identified": "MEDIUM",
                "fix_will_work": "MEDIUM"
            }
        )
    )

    pivot_state = State(
        goal=state_example.goal,
        tasks=state_example.tasks,
        active=ActiveTask(id=2, archetype="DIAGNOSE", phase="EVIDENCE_GATHERING", turns=11),
        facts=[
            Fact(
                id=9,
                desc="storage-volume-xyz disk IO wait time: 800ms (baseline: 5ms, z=15.2)",
                turn=10,
                layer="INFRASTRUCTURE"
            )
        ],
        ruled_out=["H1 (database-1 slow queries): Database is victim of storage degradation - turn 10"],
        unknowns=["What caused storage IO contention?"],
        diagnosis=Diagnosis(
            competingHypotheses=[
                CompetingHypothesis(
                    id="H4",
                    claim="storage-volume-xyz IO contention causing database slowdown",
                    layer="INFRASTRUCTURE",
                    prior_confidence=0.85,
                    current_confidence=0.85,
                    status="ACTIVE",
                    evidence_for=["factID: 9 - Disk IO wait time 160× baseline"],
                    evidence_against=[]
                )
            ]
        )
    )

    pivot_response = ParsedLLMResponse(
        reflect=pivot_reflect,
        strategize=StrategizeSection(
            reasoning="Phase 4 revealed database-1 is a victim, not the source. storage-volume-xyz has severe disk IO degradation. New hypothesis H4: storage IO contention is root cause (prior: 0.85). Returning to Phase 2.",
            hypothesis=Hypothesis(
                claim="H4: storage-volume-xyz experiencing IO contention or degradation",
                test="check_instance_health(storage-volume-xyz) and compare_metrics for disk metrics",
                signal="High disk IO wait times, high iops, or disk queue depth"
            ),
            ifInvalidated="If storage metrics normal, investigate network layer or other shared infrastructure"
        ),
        state=pivot_state,
        act=ActSection(
            tool="compare_metrics",
            params={
                "component_name": "storage-volume-xyz",
                "metric_focus": "disk"
            }
        ),
        is_finish=False,
        raw_response=""
    )

    # Return formatted JSON strings
    # IMPORTANT: Use by_alias=True to match JSON schema field names (e.g., "description" not "desc")
    return {
        "complete_response_example": json.dumps(complete_response.model_dump(exclude={"is_finish", "raw_response"}, by_alias=True), indent=2),
        "success_path_example": json.dumps(success_response.model_dump(exclude={"is_finish", "raw_response"}, by_alias=True), indent=2),
        "pivot_path_example": json.dumps(pivot_response.model_dump(exclude={"is_finish", "raw_response"}, by_alias=True), indent=2),
        "fact_example": json.dumps(fact_example.model_dump(by_alias=True), indent=2),
        "timeline_event_example": json.dumps(timeline_example.model_dump(by_alias=True), indent=2),
        "context_example": json.dumps(context_example.model_dump(by_alias=True), indent=2),
        "symptom_example": json.dumps(symptom_example.model_dump(by_alias=True), indent=2),
        "causal_link_example": json.dumps(causal_link_example.model_dump(by_alias=True), indent=2),
        "competing_hypothesis_example": json.dumps(competing_hypothesis_example.model_dump(by_alias=True), indent=2),
        "diagnosis_example": json.dumps(diagnosis_example.model_dump(by_alias=True), indent=2),
        "task_example": json.dumps(task_example.model_dump(by_alias=True), indent=2),
        "active_task_example": json.dumps(active_task_example.model_dump(by_alias=True), indent=2),
        "hypothesis_example": json.dumps(hypothesis_example.model_dump(by_alias=True), indent=2),
        "diagnostic_metadata_example": json.dumps(diagnostic_metadata_example.model_dump(by_alias=True), indent=2),
        "failure_metadata_example": json.dumps(failure_metadata_example.model_dump(by_alias=True), indent=2),
        "reflect_example": json.dumps(reflect_example.model_dump(by_alias=True), indent=2),
        "strategize_example": json.dumps(strategize_example.model_dump(by_alias=True), indent=2),
        "state_example": json.dumps(state_example.model_dump(by_alias=True), indent=2),
        "act_example": json.dumps(act_example.model_dump(by_alias=True), indent=2),
    }


def get_compact_examples() -> Dict[str, str]:
    """
    Get compact single-line examples for inline use in prompts.
    Useful for showing field structure without taking up vertical space.
    """
    examples = generate_schema_examples()

    # Convert multi-line JSON to compact single-line format
    compact = {}
    for key, json_str in examples.items():
        # Parse and re-serialize without indentation
        obj = json.loads(json_str)
        compact[key] = json.dumps(obj, separators=(',', ':'))

    return compact
