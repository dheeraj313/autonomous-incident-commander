import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from . import config, db, orchestrator, postmortem
from .auth import require_admin_key
from .models import StartIncidentRequest

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["http_client"] = httpx.AsyncClient(timeout=20.0)
    state["pool"] = await db.create_pool()
    yield
    await state["http_client"].aclose()
    await state["pool"].close()


app = FastAPI(title="AIC Incident Store", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "UP"}


@app.post("/incidents/start")
async def start_incident(request: StartIncidentRequest | None = None):
    request = request or StartIncidentRequest()
    return await orchestrator.start_incident(
        state["pool"],
        state["http_client"],
        request.root_cause_report,
        request.lookback_minutes,
        request.max_traces,
    )


@app.post("/incidents/{incident_id}/sync")
async def sync_incident(incident_id: uuid.UUID):
    result = await orchestrator.sync_incident(state["pool"], state["http_client"], incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident_id": str(incident_id), **result}


@app.get("/incidents")
async def list_incidents():
    rows = await db.fetch_incident_ids(state["pool"])
    summaries = []
    for row in rows:
        events = await db.fetch_events(state["pool"], row["incident_id"])
        ranked_event = next((e for e in events if e["event_type"] == "ROOT_CAUSE_RANKED"), None)
        top_cause = None
        if ranked_event and ranked_event["payload"].get("ranked_causes"):
            top_cause = ranked_event["payload"]["ranked_causes"][0]["service"]
        last_event = events[-1] if events else None
        summaries.append(
            {
                "incident_id": str(row["incident_id"]),
                "started_at": row["started_at"],
                "last_event_at": row["last_event_at"],
                "event_count": row["event_count"],
                "status": last_event["event_type"] if last_event else "UNKNOWN",
                "top_root_cause": top_cause,
            }
        )
    return summaries


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: uuid.UUID):
    events = await db.fetch_events(state["pool"], incident_id)
    if not events:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident_id": str(incident_id), "events": events}


@app.get("/incidents/{incident_id}/postmortem", response_class=PlainTextResponse)
async def get_postmortem(incident_id: uuid.UUID):
    events = await db.fetch_events(state["pool"], incident_id)
    if not events:
        raise HTTPException(status_code=404, detail="incident not found")
    return postmortem.generate(incident_id, events)


@app.post("/incidents/{incident_id}/resolve", dependencies=[Depends(require_admin_key)])
async def resolve_incident(incident_id: uuid.UUID, note: str | None = None):
    events = await db.fetch_events(state["pool"], incident_id)
    if not events:
        raise HTTPException(status_code=404, detail="incident not found")
    return await db.append_event(state["pool"], incident_id, "RESOLVED", {"note": note or "manually resolved"})
