import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .k8s_service import create_agent_job

app = FastAPI(title="OATS SRE Co-Pilot API")

class InvestigationRequest(BaseModel):
    goal: str
    target_namespace: str = "default"

@app.post("/investigate")
async def start_investigation(request: InvestigationRequest):
    """
    Receives an investigation goal and creates a Kubernetes Job to run the agent.
    """
    try:
        job_name, job_id = create_agent_job(
            goal=request.goal,
            namespace=request.target_namespace
        )
        return {
            "message": "Investigation started successfully.",
            "job_name": job_name,
            "job_id": job_id,
            "command_to_check_logs": f"kubectl logs -f job/{job_name} -n {request.target_namespace}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Kubernetes Job: {str(e)}")