import os
from kubernetes import client, config
import uuid

# Load Kubernetes configuration
try:
    # Try to load in-cluster config first
    config.load_incluster_config()
except config.ConfigException:
    # Fallback to kube-config for local development
    config.load_kube_config()

batch_v1 = client.BatchV1Api()

AGENT_IMAGE = os.environ.get("AGENT_IMAGE", "oats-agent:latest")
API_KEY_SECRET_NAME = os.environ.get("API_KEY_SECRET_NAME", "oats-api-keys")

def create_agent_job(goal: str, namespace: str = "default"):
    """
    Dynamically creates a Kubernetes Job to run the SRE agent.
    """
    job_name = f"oats-agent-run-{uuid.uuid4().hex[:8]}"

    # Define environment variables for the agent container
    # [cite_start]The agent already knows how to read API keys from the environment [cite: 1414, 1417]
    env_vars = [
        client.V1EnvVar(name="OATS_GOAL", value=goal),
        client.V1EnvVar(
            name="OPENAI_API_KEY",
            value_from=client.V1EnvVarSource(
                secret_key_ref=client.V1SecretKeySelector(
                    name=API_KEY_SECRET_NAME, key="openai-api-key"
                )
            ),
        ),
    ]

    # Define the container for the Job
    container = client.V1Container(
        name="oats-agent",
        image=AGENT_IMAGE,
        env=env_vars,
    )

    # Define the Pod template
    pod_template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(restart_policy="Never", containers=[container])
    )

    # Define the Job spec
    job_spec = client.V1JobSpec(
        template=pod_template,
        backoff_limit=1,
        ttl_seconds_after_finished=300 # Automatically clean up finished jobs
    )

    # Create the full Job object
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name),
        spec=job_spec,
    )

    # Create the Job in the specified namespace
    api_response = batch_v1.create_namespaced_job(body=job, namespace=namespace)

    return job_name, api_response.metadata.uid