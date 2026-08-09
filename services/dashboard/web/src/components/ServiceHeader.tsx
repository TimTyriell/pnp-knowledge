import type { ServiceStatus } from "../types";

function stateColor(state: string | undefined): string {
  switch (state) {
    case "ok":
      return "var(--ok)";
    case "stale":
      return "var(--warn)";
    default:
      return "var(--bad)";
  }
}

function stateLabel(s: ServiceStatus): string {
  if (s.state === "ok") return "läuft";
  if (s.state === "stale") return "veraltet";
  if (s.state === "offline") return "nicht erreichbar";
  if (s.state === "missing") return "keine Daten";
  return "unbekannt";
}

function Pill({ name, status }: { name: string; status: ServiceStatus }) {
  const lastRun = status.last_run;
  return (
    <div className="pill">
      <span className="pill-dot" style={{ background: stateColor(status.state) }} />
      <div className="pill-body">
        <div className="pill-title">{name}</div>
        <div className="pill-sub">{stateLabel(status)}</div>
        {lastRun && (
          <div className="pill-run">
            letzter Run: {lastRun.ended_at ? new Date(lastRun.ended_at).toLocaleString("de-DE") : "—"}
            {!lastRun.ok && <span className="pill-error"> · fehlgeschlagen</span>}
          </div>
        )}
        {status.error && <div className="pill-error">{status.error}</div>}
      </div>
    </div>
  );
}

export function ServiceHeader({
  crawl,
  kb,
  exportStatus,
}: {
  crawl: ServiceStatus;
  kb: ServiceStatus;
  exportStatus: ServiceStatus;
}) {
  return (
    <div className="service-header">
      <Pill name="pnp-crawl" status={crawl} />
      <Pill name="pnp-kb" status={kb} />
      <Pill name="pnp-export-data" status={exportStatus} />
    </div>
  );
}
