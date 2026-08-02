// Dashboard config: which host/ports to reach the read-only engines on.
// Defaults to whatever host the dashboard itself was loaded from (so this
// works whether you're on localhost or a remote docker host), on the fixed
// ports those engines are published on in docker-compose.yml.
window.AIC_CONFIG = {
  causalAnalysisBaseUrl: `http://${window.location.hostname}:8090`,
  incidentStoreBaseUrl: `http://${window.location.hostname}:8092`,
  pollIntervalMs: 5000,
};
