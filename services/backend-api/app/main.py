"""
FastAPI Backend for OATS Cloud
Creates and manages Kubernetes Jobs for agent execution
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from .k8s_service import KubernetesService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OATS Backend API",
    description="Backend API for managing OATS SRE Agent jobs on Kubernetes",
    version="1.0.0"
)

# Initialize K8s service
k8s_service = KubernetesService()


class AgentJobRequest(BaseModel):
    """Request model for creating an agent job"""
    goal: str
    max_turns: Optional[int] = 15
    environment: Optional[Dict[str, str]] = None
    timeout_seconds: Optional[int] = 3600


class AgentJobResponse(BaseModel):
    """Response model for agent job operations"""
    job_id: str
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "service": "oats-backend-api"}


@app.post("/api/v1/jobs", response_model=AgentJobResponse)
async def create_agent_job(request: AgentJobRequest):
    """
    Create a new OATS agent job in Kubernetes

    Args:
        request: Job configuration including goal and parameters

    Returns:
        AgentJobResponse with job ID and status
    """
    try:
        logger.info(f"Creating agent job for goal: {request.goal}")

        job_id = await k8s_service.create_agent_job(
            goal=request.goal,
            max_turns=request.max_turns,
            environment=request.environment,
            timeout_seconds=request.timeout_seconds
        )

        return AgentJobResponse(
            job_id=job_id,
            status="created",
            message="Agent job created successfully",
            details={"goal": request.goal, "max_turns": request.max_turns}
        )
    except Exception as e:
        logger.error(f"Failed to create agent job: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=AgentJobResponse)
async def get_job_status(job_id: str):
    """
    Get status of an agent job

    Args:
        job_id: Kubernetes job ID

    Returns:
        AgentJobResponse with current status
    """
    try:
        status = await k8s_service.get_job_status(job_id)

        return AgentJobResponse(
            job_id=job_id,
            status=status["status"],
            message=f"Job status: {status['status']}",
            details=status
        )
    except Exception as e:
        logger.error(f"Failed to get job status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """
    Get logs from an agent job

    Args:
        job_id: Kubernetes job ID

    Returns:
        Job logs
    """
    try:
        logs = await k8s_service.get_job_logs(job_id)
        return {"job_id": job_id, "logs": logs}
    except Exception as e:
        logger.error(f"Failed to get job logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Delete an agent job

    Args:
        job_id: Kubernetes job ID

    Returns:
        Deletion confirmation
    """
    try:
        await k8s_service.delete_job(job_id)
        return {"job_id": job_id, "status": "deleted", "message": "Job deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete job: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
