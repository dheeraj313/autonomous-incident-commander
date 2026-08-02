import uuid

import asyncpg
import httpx

from . import config, db
from .models import EventType

ACTION_EVENT_TYPES = ("ACTION_PROPOSED", "ACTION_APPROVED", "ACTION_EXECUTED", "ACTION_REJECTED", "ACTION_FAILED")
TERMINAL_STATUSES = {"EXECUTED", "REJECTED", "FAILED"}
_STATUS_TO_EVENT_TYPE = {
    "EXECUTED": EventType.ACTION_EXECUTED,
    "REJECTED": EventType.ACTION_REJECTED,
    "FAILED": EventType.ACTION_FAILED,
}


async def start_incident(
    pool: asyncpg.Pool,
    http_client: httpx.AsyncClient,
    root_cause_report: dict | None,
    lookback_minutes: int | None,
    max_traces: int | None,
) -> dict:
    """Detect (or accept an override of) a root-cause report, persist the
    DETECTED/ROOT_CAUSE_RANKED events, hand it to the remediation engine, and
    persist every proposed/executed/skipped action as its own event."""
    if root_cause_report is None:
        params: dict = {}
        if lookback_minutes is not None:
            params["lookback_minutes"] = lookback_minutes
        if max_traces is not None:
            params["max_traces"] = max_traces
        resp = await http_client.get(f"{config.CAUSAL_ANALYSIS_URL}/root-cause", params=params)
        resp.raise_for_status()
        root_cause_report = resp.json()

    if not root_cause_report.get("incident_detected"):
        return {"incident_detected": False, "incident_id": None}

    incident_id = uuid.uuid4()

    await db.append_event(
        pool, incident_id, EventType.DETECTED.value, {"anomalies": root_cause_report.get("anomalies", [])}
    )
    await db.append_event(
        pool,
        incident_id,
        EventType.ROOT_CAUSE_RANKED.value,
        {"ranked_causes": root_cause_report.get("ranked_causes", [])},
    )

    # Pass the exact same report we just ranked/persisted to the remediation
    # engine, so what's acted on is guaranteed consistent with what was recorded.
    remediate_resp = await http_client.post(
        f"{config.REMEDIATION_URL}/remediate",
        json={"root_cause_report": root_cause_report},
        headers={"X-Admin-Api-Key": config.ADMIN_API_KEY},
    )
    remediate_resp.raise_for_status()
    remediation = remediate_resp.json()

    for action in remediation.get("actions", []):
        await db.append_event(pool, incident_id, EventType.ACTION_PROPOSED.value, action)
        event_type = _STATUS_TO_EVENT_TYPE.get(action.get("status"))
        if event_type:
            await db.append_event(pool, incident_id, event_type.value, action)

    for skipped in remediation.get("skipped", []):
        await db.append_event(pool, incident_id, EventType.ACTION_SKIPPED.value, skipped)

    return {"incident_detected": True, "incident_id": str(incident_id), "remediation": remediation}


async def sync_incident(pool: asyncpg.Pool, http_client: httpx.AsyncClient, incident_id: uuid.UUID) -> dict | None:
    """Poll the remediation engine for status changes (approve/reject/execute
    can happen well after start_incident() returned) and append a new event
    for each transition observed since the last sync."""
    events = await db.fetch_events(pool, incident_id)
    if not events:
        return None

    latest_status_by_action: dict[str, str] = {}
    for event in events:
        if event["event_type"] in ACTION_EVENT_TYPES:
            action_id = event["payload"].get("id")
            if action_id:
                latest_status_by_action[action_id] = event["payload"].get("status")

    new_events = []
    for action_id, last_status in latest_status_by_action.items():
        resp = await http_client.get(f"{config.REMEDIATION_URL}/actions/{action_id}")
        if resp.status_code != 200:
            continue
        action = resp.json()
        current_status = action.get("status")
        if current_status != last_status:
            event_type = _STATUS_TO_EVENT_TYPE.get(current_status)
            if event_type:
                new_row = await db.append_event(pool, incident_id, event_type.value, action)
                new_events.append(new_row)
                latest_status_by_action[action_id] = current_status

    all_terminal = all(status in TERMINAL_STATUSES for status in latest_status_by_action.values())
    return {"new_events": new_events, "all_actions_terminal": all_terminal}
