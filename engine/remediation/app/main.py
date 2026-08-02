import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import docker
import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import actions, audit, config, guardrails, policy
from .auth import require_admin_key
from .models import ActionStatus, ActionType, RemediateRequest, RemediationAction, RemediationResponse

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["http_client"] = httpx.AsyncClient(timeout=15.0)
    state["redis_client"] = redis.from_url(config.REDIS_URL, decode_responses=True)
    state["docker_client"] = docker.from_env()
    yield
    await state["http_client"].aclose()
    await state["redis_client"].aclose()
    state["docker_client"].close()


app = FastAPI(title="AIC Remediation Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "UP"}


@app.get("/policies")
async def policies():
    return {
        "circuit_breaker_capable_services": config.CIRCUIT_BREAKER_CAPABLE_SERVICES,
        "fault_injection_capable_services": list(config.FAULT_INJECTION_PORTS.keys()),
        "auto_approved_actions": config.AUTO_APPROVED_ACTIONS,
        "max_actions_per_service": config.MAX_ACTIONS_PER_SERVICE,
        "action_rate_limit_window_seconds": config.ACTION_RATE_LIMIT_WINDOW_SECONDS,
        "blast_radius_max_services": config.BLAST_RADIUS_MAX_SERVICES,
    }


@app.post("/remediate", response_model=RemediationResponse, dependencies=[Depends(require_admin_key)])
async def remediate(request: RemediateRequest | None = None):
    request = request or RemediateRequest()

    if request.root_cause_report is not None:
        root_cause_report = request.root_cause_report
    else:
        params = {}
        if request.lookback_minutes is not None:
            params["lookback_minutes"] = request.lookback_minutes
        if request.max_traces is not None:
            params["max_traces"] = request.max_traces
        resp = await state["http_client"].get(f"{config.CAUSAL_ANALYSIS_URL}/root-cause", params=params)
        resp.raise_for_status()
        root_cause_report = resp.json()

    if not root_cause_report.get("incident_detected"):
        return RemediationResponse(incident_detected=False, actions=[], skipped=[])

    candidates, skipped = policy.decide_actions(root_cause_report)
    executed_actions: list[RemediationAction] = []

    for candidate in candidates:
        service = candidate["service"]
        action_type: ActionType = candidate["action_type"]
        reason = candidate["reason"]

        allowed, block_reason = await guardrails.check_and_record(state["redis_client"], service)
        if not allowed:
            skipped.append({"service": service, "action_type": action_type, "reason": block_reason})
            continue

        requires_approval = action_type.value not in config.AUTO_APPROVED_ACTIONS
        action = RemediationAction(
            id=str(uuid.uuid4()),
            service=service,
            action_type=action_type,
            reason=reason,
            requires_approval=requires_approval,
            status=ActionStatus.PENDING_APPROVAL,
        )

        if not requires_approval:
            await _execute_and_record(action)
        else:
            audit.add(action)

        executed_actions.append(action)

    return RemediationResponse(incident_detected=True, actions=executed_actions, skipped=skipped)


@app.get("/actions", response_model=list[RemediationAction])
async def list_actions():
    return audit.list_all()


@app.get("/actions/{action_id}", response_model=RemediationAction)
async def get_action(action_id: str):
    action = audit.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@app.post("/actions/{action_id}/approve", response_model=RemediationAction, dependencies=[Depends(require_admin_key)])
async def approve_action(action_id: str):
    action = audit.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    if action.status != ActionStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"action is {action.status}, not PENDING_APPROVAL")
    await _execute_and_record(action)
    return action


@app.post("/actions/{action_id}/reject", response_model=RemediationAction, dependencies=[Depends(require_admin_key)])
async def reject_action(action_id: str):
    action = audit.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    if action.status != ActionStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"action is {action.status}, not PENDING_APPROVAL")
    action.status = ActionStatus.REJECTED
    audit.update(action)
    return action


async def _execute_and_record(action: RemediationAction) -> None:
    try:
        result = await actions.execute(state["docker_client"], state["http_client"], action.service, action.action_type)
        action.status = ActionStatus.EXECUTED
        action.result = result
    except Exception as exc:  # noqa: BLE001 - genuinely want to capture and record any executor failure
        action.status = ActionStatus.FAILED
        action.result = f"{type(exc).__name__}: {exc}"
    action.executed_at = datetime.now(timezone.utc)
    audit.add(action) if audit.get(action.id) is None else audit.update(action)
