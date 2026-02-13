from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.models.user import User
from app.models.execution import Language, Execution, ExecutionStatus
from app.security.auth import get_current_user
from app.services.usage_tracker import UsageTracker
from app.sandboxes.docker_sandbox import DockerSandbox
import uuid
import json
from datetime import datetime

router = APIRouter()


class ExecuteRequest(BaseModel):
    language: Language
    code: str
    timeout: Optional[int] = None


class ExecuteResponse(BaseModel):
    execution_id: int
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    execution_time_ms: Optional[float] = None
    memory_used_mb: Optional[float] = None
    security_violations: list = []
    remaining_runs: dict


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(
    request: ExecuteRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None)
):
    """Execute code in a secure sandbox"""

    # Generate session ID if not provided
    session_id = x_session_id or str(uuid.uuid4())

    # Check usage limits
    usage_tracker = UsageTracker(db)
    usage_tracker.check_and_increment(current_user, session_id)

    # Create execution record
    execution = Execution(
        user_id=current_user.id if current_user else None,
        session_id=session_id,
        language=request.language,
        code=request.code,
        status=ExecutionStatus.PENDING
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # Execute in sandbox
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.utcnow()
    db.commit()

    sandbox = DockerSandbox()
    result = await sandbox.execute(
        language=request.language,
        code=request.code,
        timeout=request.timeout
    )

    # Update execution record
    execution.status = ExecutionStatus(result["status"])
    execution.output = result.get("output")
    execution.error = result.get("error")
    execution.exit_code = result.get("exit_code")
    execution.execution_time_ms = result.get("execution_time_ms")
    execution.memory_used_mb = result.get("memory_used_mb")
    execution.security_violations = json.dumps(result.get("security_violations", []))
    execution.container_id = result.get("container_id")
    execution.completed_at = datetime.utcnow()

    # Mark as security violation if detected
    if result.get("security_violations"):
        execution.status = ExecutionStatus.SECURITY_VIOLATION

    db.commit()
    db.refresh(execution)

    # Get remaining runs
    remaining_runs = usage_tracker.get_remaining_runs(current_user, session_id)

    return ExecuteResponse(
        execution_id=execution.id,
        status=execution.status.value,
        output=execution.output,
        error=execution.error,
        exit_code=execution.exit_code,
        execution_time_ms=execution.execution_time_ms,
        memory_used_mb=execution.memory_used_mb,
        security_violations=json.loads(execution.security_violations or "[]"),
        remaining_runs=remaining_runs
    )


@router.get("/usage")
async def get_usage(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None)
):
    """Get usage information and remaining runs"""
    session_id = x_session_id or str(uuid.uuid4())

    usage_tracker = UsageTracker(db)
    remaining = usage_tracker.get_remaining_runs(current_user, session_id)

    return {
        "user": current_user.email if current_user else None,
        "tier": current_user.tier.value if current_user else "anonymous",
        "is_employee": current_user.is_employee if current_user else False,
        **remaining
    }


@router.get("/languages")
async def list_languages():
    """List supported programming languages"""
    return {
        "languages": [
            {"name": "Python", "value": "python"},
            {"name": "PHP", "value": "php"},
            {"name": "Perl", "value": "perl"},
            {"name": "JavaScript", "value": "javascript"},
            {"name": "Node.js", "value": "node"},
            {"name": "Go", "value": "go"},
            {"name": "Shell", "value": "shell"},
            {"name": "HTML", "value": "html"},
        ]
    }
