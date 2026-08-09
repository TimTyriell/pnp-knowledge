import type { ServiceStatus } from "../types";

export function KbPanel({ kb }: { kb: ServiceStatus }) {
  const counts = kb.counts_by_type ?? {};
  return (
    <section className="panel">
      <h2>Wissensbasis</h2>
      <div className="muted">
        HEAD {kb.head ?? "—"} · Tags: {kb.session_tags?.length ?? 0} · Konflikte: {kb.conflicts?.length ?? 0}
      </div>
      <div className="chip-row">
        {Object.entries(counts).map(([type, n]) => (
          <span className="chip" key={type}>
            {type}: {n}
          </span>
        ))}
      </div>
    </section>
  );
}
