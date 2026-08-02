const cfg = window.AIC_CONFIG;

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} -> ${resp.status}`);
  return resp.json();
}

function setConnPill(id, ok) {
  const el = document.getElementById(id);
  el.className = `pill ${ok ? "pill-ok" : "pill-error"}`;
}

function fmtPct(x) {
  return x === null || x === undefined ? "-" : `${(x * 100).toFixed(1)}%`;
}

function fmtRatio(x) {
  return x === null || x === undefined ? "-" : `${x.toFixed(2)}x`;
}

async function refreshAnomalies() {
  const tbody = document.querySelector("#anomalies-table tbody");
  try {
    const anomalies = await fetchJson(`${cfg.causalAnalysisBaseUrl}/anomalies`);
    setConnPill("conn-causal", true);
    tbody.innerHTML = "";
    for (const a of anomalies) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${a.service}</td>
        <td>${a.recent_request_rate?.toFixed(2) ?? "-"}</td>
        <td>${fmtPct(a.recent_error_rate)}</td>
        <td>${fmtRatio(a.latency_ratio)}</td>
        <td class="${a.is_anomalous ? "status-anomalous" : "status-healthy"}">${a.is_anomalous ? "ANOMALOUS" : "healthy"}</td>
        <td>${(a.reasons || []).join("; ")}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    setConnPill("conn-causal", false);
    console.error(err);
  }
}

async function refreshIncidents() {
  const tbody = document.querySelector("#incidents-table tbody");
  try {
    const incidents = await fetchJson(`${cfg.incidentStoreBaseUrl}/incidents`);
    setConnPill("conn-incident", true);
    tbody.innerHTML = "";
    const sorted = [...incidents].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
    for (const inc of sorted) {
      const tr = document.createElement("tr");
      tr.className = "clickable";
      tr.innerHTML = `
        <td>${new Date(inc.started_at).toLocaleString()}</td>
        <td>${inc.status}</td>
        <td>${inc.top_root_cause ?? "-"}</td>
        <td>${inc.event_count}</td>
      `;
      tr.addEventListener("click", () => showIncidentDetail(inc.incident_id));
      tbody.appendChild(tr);
    }
  } catch (err) {
    setConnPill("conn-incident", false);
    console.error(err);
  }
}

async function showIncidentDetail(incidentId) {
  document.getElementById("detail-empty").classList.add("hidden");
  document.getElementById("detail-content").classList.remove("hidden");

  const [detail, postmortem] = await Promise.all([
    fetchJson(`${cfg.incidentStoreBaseUrl}/incidents/${incidentId}`),
    fetch(`${cfg.incidentStoreBaseUrl}/incidents/${incidentId}/postmortem`).then((r) => r.text()),
  ]);

  const tbody = document.querySelector("#timeline-table tbody");
  tbody.innerHTML = "";
  for (const event of detail.events) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${event.sequence_no}</td>
      <td>${new Date(event.created_at).toLocaleTimeString()}</td>
      <td>${event.event_type}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById("postmortem-view").textContent = postmortem;
}

async function refreshAll() {
  await Promise.all([refreshAnomalies(), refreshIncidents()]);
}

document.getElementById("refresh-btn").addEventListener("click", refreshAll);
refreshAll();
setInterval(refreshAll, cfg.pollIntervalMs);
