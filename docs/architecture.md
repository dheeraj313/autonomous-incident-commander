# Architecture Notes

## Design goals
- Zero external cost: everything runs via Docker Compose on a laptop.
- Realistic production patterns over toy simplicity: KRaft Kafka (no ZK),
  auto-instrumentation via OTel Java agent, Actuator/Micrometer for metrics,
  event-sourced incident store, policy-guarded automation instead of blind auto-heal.
- Each phase must be independently runnable and demoable (docker compose up),
  not a big-bang integration at the end.

## Telemetry signal split (why three different paths)
- **Traces:** OpenTelemetry Java agent (auto-instrumentation, zero code changes)
  → OTLP gRPC → otel-collector → Tempo. The collector is a real hop (not a
  direct agent-to-Tempo pipe) so we can add sampling/processors later without
  touching service code.
- **Metrics:** Micrometer + Spring Boot Actuator `/actuator/prometheus`,
  scraped directly by Prometheus. Keeps metrics cardinality/collection under
  Spring's control and avoids duplicating a metrics pipeline through OTel.
- **Logs:** Promtail scrapes Docker container stdout via the Docker socket and
  ships to Loki. Avoids needing structured OTel log exporters in every service
  for phase 1; logs are still correlated to traces/services via labels.

## Root-cause ranking (implemented in Phase 4, see full section below)
1. Pull recent traces from Tempo for the incident time window.
2. Build/refresh a directed service dependency graph (caller -> callee) with
   edge weights = call volume, latency, error rate.
3. Score each node using a blend of: local anomaly severity (recent vs.
   baseline window from Prometheus), graph propagation (how many upstream
   callers / downstream callees are also anomalous), and recency.
4. Rank nodes descending; highest score = suspected root cause.

## Remediation guardrails (implemented in Phase 5, see full section below)
- Every action passes through a policy check before execution:
  max actions per service per time window, blast-radius limit (max distinct
  services touched per incident), and an `approval-required` gate for
  high-risk actions (container restart) that pause for manual approval via API.
- Decisions are currently kept in an in-memory audit log inside the
  remediation-engine process; Phase 6's incident event store will make this
  durable (Postgres, append-only) so a replay can reconstruct the full
  decision path later.

## Deployment notes / gotchas hit in Phase 1
- Kafka runs as `apache/kafka:latest` (official image, KRaft combined mode,
  no Zookeeper). Bitnami's older versioned tags (e.g. `bitnami/kafka:3.7`)
  were removed from Docker Hub, so avoid pinning to old Bitnami tags.
- otel-collector's OTLP host ports are mapped to 24317/24318 instead of the
  standard 4317/4318 because Windows/Hyper-V excludes that port range on this
  machine (`netsh interface ipv4 show excludedportrange protocol=tcp`).
  Internal Docker network calls (`otel-collector:4317`) are unaffected.
- Every instrumented service sets `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` because
  the OTel Java agent defaults to OTLP/HTTP, which doesn't match the
  collector's gRPC receiver on port 4317.
- The custom gateway reverse proxy strips hop-by-hop headers (Content-Length,
  Transfer-Encoding, Connection, Host) from both forwarded requests and
  proxied responses to avoid corrupting HTTP/1.1 framing.

## Phase 3: full service chain + resilience

### Order orchestration (saga-style, non-compensating)
`orders-service` orchestrates order creation as a sequence of calls rather than
a single local transaction:
1. Validate the bearer token against `auth-service`.
2. Persist the `Order` row with status `CREATED`, publish `ORDER_CREATED`.
3. Reserve inventory via `inventory-service` (`POST /api/inventory/reserve`).
   - Success → status `INVENTORY_RESERVED`.
   - `409 Conflict` (insufficient stock) → status `INVENTORY_FAILED`, stop.
   - Any other failure (timeout/5xx/connection error) → status
     `INVENTORY_FAILED`, and this failure is recorded against the circuit
     breaker (see below).
4. If inventory was reserved, charge payment via `payments-service`
   (`POST /api/payments/charge`) for `unitPrice * quantity`.
   - Success → status `COMPLETED`.
   - Failure → status `PAYMENT_FAILED`, recorded against the circuit breaker.
5. Persist the final status and publish `ORDER_<status>` to `order-events`.

This is intentionally **not** a compensating saga: if payment fails after
inventory was already decremented, the reservation is not released. A real
system would need a compensating "release reservation" step (or an outbox +
saga coordinator); this sandbox keeps the flow simple to keep the focus on
observability/remediation rather than distributed-transaction correctness.

### Business failure vs. infrastructure failure
The circuit breaker must not trip on legitimate business outcomes (e.g. a
customer trying to order more than is in stock), only on infrastructure
degradation. `InventoryClient` reflects this by re-throwing the downstream
`409` as-is (business failure) while mapping every other exception (timeout,
connection refused, 5xx) to a `503` (infrastructure failure). In
`OrderService`, only the `503` case calls `circuitBreakerService.recordFailure()`.
`payments-service` has no real payment provider, so any failure calling it is
always treated as infrastructure.

### Redis-backed circuit breaker
Implemented in `orders-service`'s `CircuitBreakerService`, one instance shared
across all downstream dependencies, keyed by service name:
- `circuit-breaker:{service}:failures` – a counter with a TTL equal to
  `aic.circuit-breaker.failure-window-seconds` (rolling failure window).
- `circuit-breaker:{service}:open` – existence of this key means the circuit
  is open; it's set with a TTL equal to `aic.circuit-breaker.open-seconds`.
  Expiry closes the circuit automatically (key-expiry doubles as a simplified
  "half-open" state — there's no explicit trial-request phase).
- Trips when `failures` reaches `aic.circuit-breaker.failure-threshold`
  (default 3 failures / 30s window / 30s open).
- When open, `orders-service` fails fast without calling the downstream
  service at all, recording status `INVENTORY_SKIPPED_CIRCUIT_OPEN` or
  `PAYMENT_SKIPPED_CIRCUIT_OPEN`.
- Manually inspectable/overridable via `GET/POST /admin/circuit-breaker/{service}`
  (`{service}` = `inventory-service` or `payments-service`), useful for demos
  and for the future remediation engine to force-open a circuit as a
  protective action.

### Kafka event topics (post-Phase 3)
| Topic | Producer | Consumer(s) |
|---|---|---|
| `auth-events` | auth-service | notifications-service |
| `order-events` | orders-service | notifications-service |
| `payment-events` | payments-service | notifications-service |
| `inventory-events` | inventory-service | *(none yet — reserved for future analysis engine)* |

`notifications-service` runs all three listeners in the same consumer group
(`notifications-service`) and treats a fault-injected drop as a warning-logged
skip rather than a consumer-thread crash, so one bad message doesn't stall the
whole topic partition.

### Bugs found and fixed during Phase 3 live testing
- `InventoryItemRepository.findBySku` originally carried a
  `@Lock(PESSIMISTIC_WRITE)` annotation used by both `reserve()` (which is
  `@Transactional`) and `getStock()` (which was not transactional). A
  pessimistic lock query requires an active transaction to acquire the row
  lock; calling it outside one threw at runtime (500 on `GET
  /api/inventory/{item}`), even though `reserve()` worked fine. Fixed by
  splitting into two repository methods — a plain `findBySku` for read paths
  and a locked `findForUpdateBySku` used only inside `reserve()` — and adding
  `@Transactional` to `getStock()` for its auto-provisioning save.
- Prometheus doesn't reload its bind-mounted `prometheus.yml` on its own
  without `--web.enable-lifecycle` (not enabled here); after adding the three
  new scrape targets, `docker compose restart prometheus` (not just `up -d`,
  which only recreates containers on service-definition changes) was needed
  to pick up the new config.

## Phase 4: causal analysis engine

`engine/causal-analysis` is a standalone Python FastAPI service (`:8090`),
deliberately dependency-light (`fastapi`, `uvicorn`, `httpx` only — no
`networkx`/`pandas`; the graph logic is plain dicts/sets/tuples).

### Tempo trace mining -> dependency graph
`GET /dependency-graph` fetches recent trace IDs from Tempo's `/api/search`,
then each full trace from `/api/traces/{id}` (OTLP-JSON: `batches[].resource`
for `service.name`, `scopeSpans[].spans[]` for `spanId`/`parentSpanId`). It
builds a `spanId -> service_name` index across all spans in a trace, then for
every span whose parent resolves to a *different* service, records a
`(caller, callee)` edge with aggregated call count, error count, and average
latency. A cross-service edge is exactly this: a span whose parent lives in
another service's resource batch.

### Anomaly detection -> Prometheus
`GET /anomalies` queries Prometheus's instant-query API against the existing
Micrometer/Actuator metrics (`http_server_requests_seconds_{count,sum}`),
comparing a short "recent" window (default `1m`) against a longer "baseline"
window (default `10m`) per service, for both error rate and average latency.
A service is anomalous if `recent_error_rate >= threshold` OR
`latency_ratio >= threshold`, gated by a minimum request rate so idle
services aren't flagged on noise. Because this uses a `rate()` window, a
transient fault burst that finishes more than ~1 minute before the query runs
will no longer show up as "recent" — this is an inherent tradeoff of
window-based rate metrics, not a bug, and was directly observed while
validating this phase (a fault-injection burst detected on an immediate query
had disappeared from `/anomalies` ~30s later once outside the window).

### Root-cause ranking
`GET /root-cause` combines the graph and the anomalies: for each anomalous
service, `score = severity * (1 + 0.5 * anomalous_upstream_callers) /
(1 + anomalous_downstream_callees)`. This favors services with many anomalous
callers (propagation evidence — the fault is spreading *from* here) and few
anomalous callees (evidence this is the deepest cause, not a victim of
something further downstream).

### Bug found and fixed during Phase 4 live testing
- **Symptom:** `/dependency-graph` always returned all 6 known services as
  `nodes` but an empty `edges` list, even with confirmed real, correctly
  linked, multi-service traces in Tempo (manually verified via TraceQL that a
  single trace ID contained spans from all of gateway, orders-service,
  auth-service, inventory-service, payments-service, and notifications-service
  with correct parent/child linkage — including across Kafka message
  boundaries into notifications-service). Distributed trace-context
  propagation itself was **not** broken; an earlier diagnosis session had
  wrongly suspected the OTel Java agent / Spring `RestClient` propagation
  based on `rootServiceName` counts alone.
- **Root cause:** Prometheus scrapes `GET /actuator/prometheus` on every
  service roughly every 15s, generating far more traces than real business
  traffic. `search_recent_trace_ids()` used a plain `/api/search?limit=N`
  query (most-recent-N traces across the whole stack), which was then almost
  entirely actuator-scrape noise — real order/auth traces got crowded out of
  the top N long before `max_traces` was reached, so the graph builder never
  saw a trace containing a genuine cross-service call.
- **Fix:** `search_recent_trace_ids()` now passes a TraceQL filter
  (`config.DEPENDENCY_GRAPH_TRACEQL_FILTER`, default
  `{resource.service.name="gateway" && span.http.route != "/actuator/prometheus"}`)
  restricting results to traces that pass through the gateway on a real route
  — every genuine cross-service call chain in this system starts there.
- **Lesson:** when a new feature depends on existing infrastructure (like a
  tracing backend), verify the *actual data* returned by real API calls before
  concluding the infrastructure itself is broken — aggregate counts
  (`rootServiceName` tallies) were misleading here because they didn't
  distinguish "genuinely disconnected trace" from "trace whose root happens to
  be a health-check/DB-warmup query with no incoming request context to
  propagate in the first place."

## Phase 5: remediation engine

`engine/remediation` is a second standalone Python FastAPI service (`:8091`),
same lean dependency footprint plus `redis` (async client) and `docker`
(Docker Engine API SDK). It turns a root-cause report into real, verifiable
actions against the running stack — nothing here is simulated.

### Policy engine (`policy.py`)
Deterministic, rule-based, evaluated per ranked anomalous service in score
order (highest first), capped at `BLAST_RADIUS_MAX_SERVICES` (remaining
ranked services are returned as blast-radius-skipped, not silently dropped):
1. Elevated error rate on a service the circuit breaker already covers
   (`inventory-service`/`payments-service`) → `TRIP_CIRCUIT_BREAKER`.
2. Elevated error rate on any other fault-injection-capable service →
   `CLEAR_FAULT_INJECTION`.
3. Elevated latency only (no elevated error rate) → `RESTART_SERVICE`.

### Actions (`actions.py`) — all real, no stubs
- `TRIP_CIRCUIT_BREAKER` — HTTP `POST` to **orders-service's own**
  `/admin/circuit-breaker/{service}/trip` (orders-service is the only service
  that owns downstream circuit breakers today, guarding its own calls to
  inventory-service/payments-service — tripping "inventory-service's breaker"
  means calling orders-service's admin API, not inventory-service's).
- `CLEAR_FAULT_INJECTION` — HTTP `DELETE` to the offending service's own
  `/admin/fault-injection`.
- `RESTART_SERVICE` — Docker Engine API (`docker-py`, via the mounted
  `/var/run/docker.sock`, read-write) `container.restart()` on `aic-{service}`.

### Guardrails (`guardrails.py` + policy layer)
- **Rate limit:** Redis TTL-counter per service (`remediation:{service}:action-count`,
  same pattern as the existing circuit breaker), max `MAX_ACTIONS_PER_SERVICE`
  actions per `ACTION_RATE_LIMIT_WINDOW_SECONDS`. A blocked candidate is
  reported in `skipped` and does **not** count against the window itself.
- **Blast radius:** only the top `BLAST_RADIUS_MAX_SERVICES` ranked causes are
  ever turned into candidates per `/remediate` call.
- **Approval gate:** actions in `AUTO_APPROVED_ACTIONS`
  (`TRIP_CIRCUIT_BREAKER`, `CLEAR_FAULT_INJECTION` — both safe/reversible)
  execute immediately; everything else (`RESTART_SERVICE` — disruptive, drops
  in-flight connections) is created `PENDING_APPROVAL` and requires a
  separate `POST /actions/{id}/approve` (or `/reject`) call.

### Audit log
`GET /actions` returns every action taken/pending this process, in-memory
only (module-level dict in `audit.py`). This is a deliberate Phase 5
simplification — Phase 6's incident event store will persist the full
decision trail durably in Postgres so it survives a process restart and
supports replay.

### Verified live end-to-end
Injected a real fault into inventory-service (`errorRate=0.9`), generated
order traffic, and called `POST /remediate` with no override (live
`/root-cause` fetch):
- `inventory-service` (error-rate anomaly) → `TRIP_CIRCUIT_BREAKER` executed
  automatically; confirmed via orders-service's own status endpoint that the
  breaker was genuinely open afterward.
- `auth-service` (latency-only anomaly, a side effect of the traffic burst) →
  `RESTART_SERVICE` correctly created as `PENDING_APPROVAL` instead of
  executing immediately.
- `gateway` and `orders-service` (also ranked, lower) → correctly reported as
  blast-radius-skipped once 2 candidates had already been selected.
- Rejected the pending auth-service restart via `POST /actions/{id}/reject`,
  then separately posted a synthetic root-cause override naming
  notifications-service and approved that restart via
  `POST /actions/{id}/approve` — confirmed via `docker ps` that the real
  container uptime reset to a few seconds afterward.
- Repeated the same synthetic candidate against notifications-service 3 more
  times in a row; the 3rd repeat was correctly blocked by the per-service
  rate-limit guardrail (`"rate limit: 3 actions already taken ... (max 3)"`).

## Phase 6: incident event store

`engine/incident-store` is a third standalone Python FastAPI service (`:8092`,
`fastapi`/`httpx`/`asyncpg` only) that turns Phases 4+5 into a durable,
replayable incident lifecycle. It owns the `incidents.incident_events` table
that's been sitting in `infra/postgres/init.sql` since Phase 1 — append-only,
`(incident_id, sequence_no)` unique, event-sourcing style: nothing is ever
`UPDATE`d or `DELETE`d, an incident's state is always derived by replaying its
events in order.

### Orchestration (`orchestrator.py`)
- `start_incident()`: fetches (or accepts a raw override of) a root-cause
  report from causal-analysis-engine, persists `DETECTED` (the anomaly list)
  and `ROOT_CAUSE_RANKED` (the ranked causes) events, then hands that *exact
  same report* to remediation-engine's `/remediate` — guaranteeing the
  persisted ranking and the executed actions are always for the same input,
  never two independently-fetched snapshots. Every action returned becomes an
  `ACTION_PROPOSED` event, immediately followed by `ACTION_EXECUTED`/
  `ACTION_FAILED` if it ran synchronously (auto-approved actions); every
  guardrail-skipped candidate becomes an `ACTION_SKIPPED` event.
- `sync_incident()`: since `RESTART_SERVICE` actions can sit in
  `PENDING_APPROVAL` indefinitely and be approved/rejected well after
  `start_incident()` returned, this polls remediation-engine's
  `GET /actions/{id}` for every action ever proposed in the incident and
  appends a new event only when the live status differs from what was last
  recorded — the append-only log is never rewritten, only extended.

### Concurrency-safe sequencing (`db.py`)
`append_event()` computes the next `sequence_no` as `MAX(sequence_no)+1` for
the incident, guarded by `pg_advisory_xact_lock(hashtext(incident_id))` inside
the same transaction — serializes concurrent appends to the *same* incident
without needing a separate counter table, while still letting unrelated
incidents append fully in parallel.

### Replay = just reading the events back
`GET /incidents/{id}` returns the full, ordered event list for an incident.
Because nothing is ever mutated, this *is* the replay — there's no separate
reconstruction step or derived-state table to keep in sync.

### Auto-generated postmortems (`postmortem.py`)
`GET /incidents/{id}/postmortem` renders that same ordered event list into
markdown (root cause ranking, actions taken with final status, guardrails
triggered, a full per-event timeline table, resolution status) — a pure
projection of the event log, not a separately maintained document.

### Bugs found during Phase 6 live testing
None. Verified live end-to-end on the first pass:
- A synthetic root-cause report for inventory-service correctly produced
  `DETECTED` → `ROOT_CAUSE_RANKED` → `ACTION_PROPOSED` → `ACTION_EXECUTED` for
  an auto-approved `TRIP_CIRCUIT_BREAKER`.
- A synthetic latency-only report for auth-service correctly stayed at
  `ACTION_PROPOSED` (`PENDING_APPROVAL`) until the action was rejected
  out-of-band directly against remediation-engine; `POST /incidents/{id}/sync`
  correctly detected that transition and appended a new `ACTION_REJECTED`
  event without touching any prior row.
- `POST /incidents/{id}/resolve` correctly appended a terminal `RESOLVED`
  event, and `/postmortem` correctly reflected the updated status/duration
  afterward.
- **Durability verified directly**, not just assumed from using Postgres:
  restarted the `incident-store` container mid-session and confirmed
  `GET /incidents/{id}` still returned the identical, correctly-ordered
  5-event history afterward — genuinely persisted, unlike remediation-engine's
  in-memory audit log from Phase 5.

## Phase 7: chaos engineering

`chaos/` is a set of plain host-side Python scripts (no container — the
scripts run directly against the stack's exposed `localhost` ports; the only
dependency is `httpx`). They inject real faults, drive real traffic through
the gateway, and measure two things empirically against the live stack rather
than asserting them: root-cause ranking precision, and MTTR reduction.

### Root-cause precision (`precision_experiment.py`)
Runs 4 scenarios (`scenarios.py`): inventory error burst, payments error
burst, auth latency spike, orders latency spike. Each scenario clears prior
faults, waits out a cooldown, injects a real fault via the target service's
own `/admin/fault-injection` endpoint, drives real traffic through the
gateway, and polls causal-analysis-engine's `/root-cause` until it reports an
incident, then checks whether the #1 ranked cause matches the actually-faulted
service. **Final measured result: 75% top-1 precision (3/4)** — see "bugs
found" below for what the first two (much lower-scoring) runs revealed and how
they were fixed.

### MTTR reduction (`mttr_experiment.py`)
Injects a real error burst into inventory-service (circuit-breaker-capable, so
remediation auto-approves with no human-approval wait — a clean, fully
automated number), drives traffic, and repeatedly calls incident-store's live
`POST /incidents/start` until an action is executed *and* confirmed (circuit
breaker actually open via orders-service's own status endpoint). That measured
automated time is compared against a **documented manual-baseline
assumption** — there is no real human in this sandbox to time, so rather than
inventing an arbitrary number, the formula is `alert_ack_seconds +
num_services_in_topology × per_service_diagnosis_seconds + fix_execution_seconds`,
where `num_services_in_topology` is fetched live from
causal-analysis-engine's `/dependency-graph` (not hardcoded), and the other
three terms are named, adjustable constants in `chaos/config.py` — explicit
about being an assumption, not a measurement. **Measured result: ~16s
automated vs. a 720s manual baseline (6-service topology) — 97.8% reduction**
against that documented assumption. Worked correctly on the very first run.

### Bugs found and fixed during Phase 7 live testing

1. **Inter-scenario contamination from the 1-minute detection window.** The
   first live run of `precision_experiment.py` used only a 2-second gap
   between scenarios. Because causal-analysis-engine's anomaly detection
   compares against a **1-minute "recent" rate() window**
   (`ANOMALY_RECENT_WINDOW`), a 2-second gap wasn't remotely enough for the
   previous scenario's fault signal (or, for the very first scenario,
   leftover signal from earlier manual testing in the same session) to age
   out of that window — 2 of 4 scenarios incorrectly reported `gateway` as
   the top cause, matching stale/leftover data rather than the newly injected
   fault. **Fix:** added `INTER_SCENARIO_COOLDOWN_SECONDS` (70s, safely longer
   than the recent window) to `chaos/config.py` and used it between every
   scenario, including before the first one.

2. **`orders-service` returned HTTP 200 even when a downstream dependency
   completely failed.** `POST /api/orders` always returned `200 OK` as long
   as the *order record itself* was saved — even when inventory reservation
   or payment charging failed outright, or was skipped because orders-service's
   own client-side circuit breaker for that dependency was open. This meant a
   downstream service failing (or having its own circuit breaker trip after
   just 3 failures, per `CircuitBreakerService`'s `failure-threshold`) never
   showed up in orders-service's *own* HTTP error rate, so
   causal-analysis-engine's purely HTTP-status-based anomaly detection (which
   only looks at `outcome=SERVER_ERROR` responses) had no error-rate signal
   to work with for that request path at all — genuinely invisible, not just
   hard to rank. Confirmed directly: repeated manual order requests during an
   injected inventory fault returned `200` every time. **Fix:** `OrderController`
   now returns `502 Bad Gateway` whenever the order's terminal status is
   `INVENTORY_FAILED`, `INVENTORY_SKIPPED_CIRCUIT_OPEN`, `PAYMENT_FAILED`, or
   `PAYMENT_SKIPPED_CIRCUIT_OPEN` — a request that didn't actually complete
   successfully now honestly reports that to the caller (and to Micrometer),
   independent of chaos testing; the chaos scripts just happened to be what
   surfaced it.
3. **Minor: `chaos/http_helpers.py`'s `generate_order_traffic` sent the wrong
   JSON field name (`sku` instead of `item`)** — `CreateOrderRequest` only
   accepts `item`/`quantity`, so every simulated order request was silently
   failing validation with `400 Bad Request` before ever reaching the order
   saga, meaning inventory/payments/orders-service never received any real
   traffic during those scenarios regardless of the other two fixes. Caught
   by manually replaying the exact request the chaos script was sending and
   observing the `400`. **Fix:** corrected the field name.

Note: one scenario (`payments_error_burst`) still misses top-1 in the final
run — `gateway` crossed the anomaly error-rate threshold a few seconds before
`payments-service` did in that particular run, an artifact of the ranking
loop stopping at the *first* detected incident rather than waiting for the
full picture to settle. Directly inspecting `/anomalies` confirmed
`payments-service`, `orders-service`, and `gateway` all become anomalous
within a few seconds of each other as traffic accumulates — this is an
inherent characteristic of real-time, streaming anomaly detection (an early
signal can be incomplete) rather than a ranking defect, and is reported
honestly rather than re-run until it disappears.

## Phase 8: hardening — admin auth, automated tests, CI, one-command demo, dashboard

Everything up to Phase 7 proved the SRE loop works. Phase 8 makes the project
presentable and safe to leave running/share: locking down every
state-changing endpoint, adding real automated test coverage, wiring up CI,
collapsing the whole demo into one command, and adding a read-only web
dashboard so the incident lifecycle can be watched without curling APIs.

### Admin-key auth
Every endpoint that changes state (fault injection, circuit-breaker trip,
remediation action approval/rejection, incident resolution, remediate/start)
now requires a shared-secret header: `X-Admin-Api-Key`, checked against the
`ADMIN_API_KEY` env var (default `dev-admin-key-change-me` — meant to be
overridden via `.env`/compose env for anything beyond local sandbox use).
This is intentionally **not** a real auth system — no users, roles, or
tokens with expiry — just a minimal guard so these endpoints aren't wide
open on a machine with ports published to the host. Implemented as:
- **Java services:** a shared `AdminAuthFilter` (`OncePerRequestFilter`)
  registered on `/admin/**` routes in each of the 5 services that expose one.
- **Python engines:** a FastAPI `Depends(require_admin_key)` guard
  (`engine/*/app/auth.py`) applied to every state-changing route.
Read-only `GET` endpoints (health, dependency-graph, anomalies, root-cause,
incidents list/detail, postmortem) are deliberately left unauthenticated so
the dashboard can poll them from the browser with no secret embedded client-side.

### Automated tests
Each Python engine has a `tests/` directory (pytest + `pytest-asyncio` where
needed) covering the pure-logic pieces that don't require the live stack:
policy selection and guardrails (remediation-engine), anomaly detection and
root-cause ranking (causal-analysis-engine), and postmortem rendering
(incident-store) — 27 tests total across the three engines, all passing.
These are unit tests against pure functions/in-memory fakes (e.g. a fake
Redis), not integration tests against the live Docker stack — that role is
already filled by the chaos scripts in Phase 7.

Each of the 6 Java services also has its own `src/test/java` unit test suite
(JUnit 5 + Mockito, already pulled in via `spring-boot-starter-test`), with
every collaborator (JPA repositories, `StringRedisTemplate`, Kafka
publishers, downstream HTTP clients) mocked — no `@SpringBootTest`, no
Testcontainers, no embedded DB/Kafka/Redis, so these run in a few seconds
per service with no external dependencies. Coverage:
- **gateway:** `ProxyServiceTest` — hop-by-hop request/response header
  stripping (`Connection`, stale `Content-Length`, `Host`, `Transfer-Encoding`),
  query-string forwarding, and pass-through of non-2xx downstream status
  codes, using `MockRestServiceServer` bound to the service's `RestClient`.
- **auth-service:** `TokenServiceTest` (Redis-backed token issue/resolve with
  TTL), `AuthServiceTest` (register/login/validate, duplicate-username and
  bad-password paths), `AdminAuthFilterTest` (admin-key enforcement).
- **orders-service:** `OrderServiceTest` (the full order saga — happy path,
  insufficient stock, inventory/payment infra failures, open-circuit-breaker
  skip paths), `CircuitBreakerServiceTest` (failure counting, trip/reset,
  status/TTL reporting), `AdminAuthFilterTest`.
- **inventory-service:** `InventoryServiceTest` (auto-provisioning unknown
  SKUs, reserve success/insufficient-stock, stock lookup), `AdminAuthFilterTest`.
- **payments-service:** `PaymentServiceTest` (charge persists and publishes
  an event), `AdminAuthFilterTest`.
- **notifications-service:** `NotificationEventListenerTest` (auth/order/
  payment event parsing and persistence, injected-fault message drop,
  malformed-payload handling), `AdminAuthFilterTest`.

### CI
`.github/workflows/ci.yml` runs on every push/PR to `main`:
- A matrix job builds and runs the unit test suite for all 6 Java services
  (`mvn package`, which runs `mvn test` as part of the default lifecycle).
- A matrix job runs `pytest` for all 3 Python engines.

### One-command demo (`demo.ps1`)
A PowerShell script at the repo root that runs the entire incident lifecycle
against the real stack in one shot: `docker compose up -d` (builds images
only if they don't exist yet — see "bugs found" below for why `--build` was
deliberately removed), waits for the 5 core services to report healthy,
registers and logs in a demo user, generates baseline traffic, injects a real
fault into inventory-service, drives load, calls incident-store to
detect+remediate, waits for the action to execute, resolves the incident,
prints the generated postmortem, and cleans up the injected fault. Requires
nothing beyond Docker Desktop and PowerShell — no manual curl commands.

### Dashboard (`dashboard/`)
A static, dependency-free HTML/CSS/vanilla-JS page (no build step, no
framework) served by its own tiny nginx container (`aic-dashboard`,
port 8095) and added to `docker-compose.yml`. It polls
causal-analysis-engine and incident-store's read-only `GET` endpoints
(`config.js` sets the poll interval and base URLs, defaulting to whatever
host the page itself was loaded from) to show: live per-service anomaly
status, a connection-status pill per engine, a list of historical incidents,
and — on clicking an incident — its full event timeline plus rendered
postmortem. Read-only by design: it never needs the admin key.

### Bugs found and fixed during Phase 8 live end-to-end validation

1. **`docker compose up -d --build` forced a full cold-restart of every
   rebuilt container on every single invocation**, even with 100%-cached
   Docker layers, because BuildKit's build attestation/manifest metadata
   differs on each build invocation, giving the resulting image a "new"
   identity each time. On this dev machine, where Spring Boot + the OTel
   Java agent can take 2-5+ minutes per service to finish starting under
   concurrent load, this turned every repeat `demo.ps1` run into a multi-
   minute cold-start cycle instead of an instant re-run. **Fix:** removed
   `--build` from `demo.ps1`'s `docker compose up` call — Compose still
   builds images that don't exist yet (so the very first run remains a true
   "one command"), but no longer force-recreates already-built, unchanged
   containers on every subsequent run.
2. **Kafka's healthcheck transiently reported "unhealthy" under heavy
   concurrent CPU load**, even though the broker itself was functioning
   normally (logs showed ongoing consumer-group rebalancing throughout).
   Kafka's healthcheck command (`kafka-topics.sh --list`) spins up its own
   JVM, which could occasionally exceed the original 10s timeout while 8
   other containers were cold-starting simultaneously — and since Compose's
   `depends_on: condition: service_healthy` check is a snapshot read (not a
   wait-and-retry loop), this was enough to abort the entire `docker compose
   up` with "dependency failed to start: container aic-kafka is unhealthy".
   **Fix:** bumped Kafka's `healthcheck.timeout` from `10s` to `30s` in
   `docker-compose.yml`.
3. **Adding admin-key auth broke server-to-server calls that were never
   updated to send the new header** — a real regression only surfaced by
   running `demo.ps1` end-to-end, not by curling each service individually:
   `incident-store`'s orchestrator called remediation-engine's `POST
   /remediate` without the header, and remediation-engine's action executor
   called `POST /admin/circuit-breaker/{service}/trip` and `DELETE
   /admin/fault-injection` without it either — both failing with `401` deep
   inside the remediation flow. **Fix:** both internal calls now send
   `X-Admin-Api-Key` from each service's own `ADMIN_API_KEY` config. General
   lesson: adding an auth guard to an admin/internal endpoint requires
   grepping for every internal caller (other services' HTTP clients), not
   just the external/demo callers — per-service unit tests don't exercise
   cross-service calls, so this class of bug only shows up in a true
   end-to-end run.

Verified live end-to-end after all three fixes: a full `demo.ps1` run
completed with zero unexpected `401`s — fault injected, incident detected,
`CLEAR_FAULT_INJECTION` and `TRIP_CIRCUIT_BREAKER` both executed,
`RESTART_SERVICE` correctly skipped by the blast-radius guardrail, postmortem
rendered, incident resolved, fault cleaned up.

The new Java unit test suites (see "Automated tests" above) were run for all
6 services via `mvn test` (using the same `maven:3.9-eclipse-temurin-17`
image as each service's Dockerfile build stage) and all pass.

