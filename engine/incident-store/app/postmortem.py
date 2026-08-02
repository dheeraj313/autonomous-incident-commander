"""Renders an incident's ordered event log into a markdown postmortem. This is
the "replay" in practice: the timeline table below is a straight, faithful
render of the append-only event sequence, in order, with nothing mutated or
reinterpreted after the fact."""

ACTION_EVENT_TYPES = ("ACTION_PROPOSED", "ACTION_APPROVED", "ACTION_EXECUTED", "ACTION_REJECTED", "ACTION_FAILED")


def _summarize_event(event: dict) -> str:
    event_type = event["event_type"]
    payload = event["payload"]

    if event_type == "DETECTED":
        return f"{len(payload.get('anomalies', []))} service(s) flagged anomalous"
    if event_type == "ROOT_CAUSE_RANKED":
        causes = payload.get("ranked_causes", [])
        if not causes:
            return "no root cause candidates ranked"
        top = causes[0]
        return f"top candidate: {top['service']} (score {top['score']:.2f})"
    if event_type in ACTION_EVENT_TYPES:
        result = f" -> {payload['result']}" if payload.get("result") else ""
        return f"{payload.get('action_type')} on {payload.get('service')} [{payload.get('status')}]{result}"
    if event_type == "ACTION_SKIPPED":
        return f"{payload.get('action_type')} on {payload.get('service')} skipped: {payload.get('reason')}"
    if event_type == "RESOLVED":
        return payload.get("note", "incident marked resolved")
    return str(payload)


def generate(incident_id, events: list[dict]) -> str:
    if not events:
        return f"# Postmortem: Incident {incident_id}\n\nNo events recorded.\n"

    started_at = events[0]["created_at"]
    last_event = events[-1]
    ended_at = last_event["created_at"]
    resolved = last_event["event_type"] == "RESOLVED"

    ranked_event = next((e for e in events if e["event_type"] == "ROOT_CAUSE_RANKED"), None)
    ranked_causes = ranked_event["payload"].get("ranked_causes", []) if ranked_event else []

    action_events = [e for e in events if e["event_type"] in ACTION_EVENT_TYPES]
    latest_action_by_id: dict[str, dict] = {}
    for e in action_events:
        latest_action_by_id[e["payload"]["id"]] = e["payload"]

    skipped_events = [e for e in events if e["event_type"] == "ACTION_SKIPPED"]

    lines: list[str] = []
    lines.append(f"# Postmortem: Incident {incident_id}")
    lines.append("")
    lines.append(f"- **Detected at:** {started_at.isoformat()}")
    lines.append(f"- **Status:** {'RESOLVED' if resolved else last_event['event_type']}")
    lines.append(f"- **Duration:** {ended_at - started_at}")
    lines.append("")

    lines.append("## Root cause")
    if ranked_causes:
        for i, c in enumerate(ranked_causes):
            marker = " **(top cause)**" if i == 0 else ""
            lines.append(f"- `{c['service']}` \u2014 score {c['score']:.2f}{marker}: {', '.join(c.get('reasons', []))}")
    else:
        lines.append("- No root cause candidates were ranked.")
    lines.append("")

    lines.append("## Actions taken")
    if latest_action_by_id:
        for action in latest_action_by_id.values():
            result = f" \u2014 {action['result']}" if action.get("result") else ""
            lines.append(
                f"- `{action['action_type']}` on `{action['service']}`: **{action['status']}**{result} "
                f"({action.get('reason')})"
            )
    else:
        lines.append("- No remediation actions were proposed.")
    lines.append("")

    lines.append("## Guardrails triggered")
    if skipped_events:
        for e in skipped_events:
            p = e["payload"]
            lines.append(f"- `{p.get('action_type')}` on `{p.get('service')}` skipped: {p.get('reason')}")
    else:
        lines.append("- None.")
    lines.append("")

    lines.append("## Timeline")
    lines.append("")
    lines.append("| # | Time | Event | Summary |")
    lines.append("|---|------|-------|---------|")
    for e in events:
        lines.append(f"| {e['sequence_no']} | {e['created_at'].isoformat()} | {e['event_type']} | {_summarize_event(e)} |")
    lines.append("")

    lines.append("## Resolution")
    lines.append(f"Resolved at {ended_at.isoformat()}." if resolved else "Not yet resolved.")

    return "\n".join(lines) + "\n"
