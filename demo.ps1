# One-command demo of the Autonomous Incident Commander:
#   1. Brings up the full stack (building images the first time only) and
#      waits for it to be healthy.
#   2. Registers/logs in a demo user and generates a little baseline traffic.
#   3. Injects a real fault (elevated error rate) into inventory-service.
#   4. Asks the incident-store to detect + remediate it live.
#   5. Polls until the remediation action executes, then prints the incident's
#      generated postmortem.
#   6. Cleans up the injected fault so the stack is left healthy.
#
# Usage:  .\demo.ps1
# Requires: Docker Desktop running, PowerShell 5.1+, ports 8080-8095/3000/9090 free.
# If you've changed source code since the last run, run `docker compose build`
# yourself first - this script intentionally does NOT pass --build on every
# run, since that forces all containers to recreate/cold-start even when
# nothing changed (slow, and needlessly disruptive on constrained machines).

$ErrorActionPreference = "Stop"
$AdminApiKey = if ($env:ADMIN_API_KEY) { $env:ADMIN_API_KEY } else { "dev-admin-key-change-me" }
$AdminHeaders = @{ "X-Admin-Api-Key" = $AdminApiKey }

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Wait-ForHealth($url, $name, $timeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 3
            if ($resp) { Write-Host "  $name is up." -ForegroundColor Green; return }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "$name did not become healthy within $timeoutSeconds seconds"
}

Write-Step "Starting the stack (docker compose up -d)"
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Step "Waiting for core services to report healthy"
# Cold JVM starts (Spring Boot + otel javaagent) can take several minutes on a
# machine that is also rebuilding/starting many containers at once, so these
# timeouts are generous rather than tight.
Wait-ForHealth "http://localhost:8080/actuator/health" "gateway" 300
Wait-ForHealth "http://localhost:8081/actuator/health" "auth-service" 300
Wait-ForHealth "http://localhost:8090/health" "causal-analysis-engine" 120
Wait-ForHealth "http://localhost:8091/health" "remediation-engine" 120
Wait-ForHealth "http://localhost:8092/health" "incident-store" 120

Write-Step "Registering a demo user and logging in"
$username = "demo-user-$([int](Get-Date -UFormat %s))"
$body = @{ username = $username; password = "demo-pass-123" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/auth/register" -Method Post -Body $body -ContentType "application/json" | Out-Null
$login = Invoke-RestMethod -Uri "http://localhost:8080/api/auth/login" -Method Post -Body $body -ContentType "application/json"
$token = $login.token
$authHeaders = @{ Authorization = "Bearer $token" }
Write-Host "  logged in as $username"

Write-Step "Generating a little baseline traffic (healthy orders)"
for ($i = 0; $i -lt 5; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8080/api/orders" -Method Post `
            -Body (@{ item = "widget"; quantity = 1 } | ConvertTo-Json) -ContentType "application/json" `
            -Headers $authHeaders | Out-Null
    } catch { }
    Start-Sleep -Milliseconds 300
}

Write-Step "Injecting a fault: 90% error rate on inventory-service"
Invoke-RestMethod -Uri "http://localhost:8083/admin/fault-injection" -Method Post `
    -Body (@{ errorRate = 0.9; latencyMs = 0 } | ConvertTo-Json) -ContentType "application/json" `
    -Headers $AdminHeaders | Out-Null

Write-Step "Generating load so the fault shows up in the metrics window"
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8080/api/orders" -Method Post `
            -Body (@{ item = "widget"; quantity = 1 } | ConvertTo-Json) -ContentType "application/json" `
            -Headers $authHeaders | Out-Null
    } catch { }
    Start-Sleep -Milliseconds 300
}

Write-Step "Asking the incident store to detect + remediate (may take a few seconds for metrics to land)"
$incident = $null
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $result = Invoke-RestMethod -Uri "http://localhost:8092/incidents/start" -Method Post `
        -Body (@{} | ConvertTo-Json) -ContentType "application/json"
    if ($result.incident_detected) { $incident = $result; break }
    Start-Sleep -Seconds 3
}

if (-not $incident) {
    Write-Host "No incident was detected in time - try re-running, or inspect http://localhost:8090/anomalies" -ForegroundColor Yellow
} else {
    $incidentId = $incident.incident_id
    Write-Host "  incident detected: $incidentId" -ForegroundColor Green

    Write-Step "Waiting for the remediation action to execute"
    $executed = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $detail = Invoke-RestMethod -Uri "http://localhost:8092/incidents/$incidentId"
        if ($detail.events | Where-Object { $_.event_type -eq "ACTION_EXECUTED" }) { $executed = $true; break }
        Start-Sleep -Seconds 2
    }
    Write-Host "  action executed: $executed"

    Write-Step "Marking the incident resolved"
    Invoke-RestMethod -Uri "http://localhost:8092/incidents/$incidentId/resolve?note=demo%20run%20complete" -Method Post -Headers $AdminHeaders | Out-Null

    Write-Step "Postmortem"
    $postmortem = Invoke-RestMethod -Uri "http://localhost:8092/incidents/$incidentId/postmortem"
    Write-Host $postmortem
}

Write-Step "Cleaning up the injected fault"
Invoke-RestMethod -Uri "http://localhost:8083/admin/fault-injection" -Method Delete -Headers $AdminHeaders | Out-Null
Invoke-RestMethod -Uri "http://localhost:8082/admin/circuit-breaker/inventory-service/reset" -Method Post -Headers $AdminHeaders | Out-Null

Write-Step "Done. Explore further:"
Write-Host "  Dashboard:  http://localhost:8095"
Write-Host "  Grafana:    http://localhost:3000  (admin/admin)"
Write-Host "  Prometheus: http://localhost:9090"
