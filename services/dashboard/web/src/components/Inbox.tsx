import type { Action } from "../types";

const KIND_LABEL: Record<string, string> = {
  unresolved_speaker: "Sprecher offen",
  pending_stage: "Nächster Schritt",
  conflict: "Konflikt",
  harvest: "Team-Text übernehmen",
  stub: "Seite fehlt",
  edited: "Von Hand bearbeitet",
  anomaly: "Auffälligkeit",
};

export function Inbox({ actions }: { actions: Action[] }) {
  const grouped = new Map<string, Action[]>();
  for (const a of actions) {
    const list = grouped.get(a.kind) ?? [];
    list.push(a);
    grouped.set(a.kind, list);
  }

  return (
    <section className="panel">
      <h2>Aktions-Inbox ({actions.length})</h2>
      {actions.length === 0 && <p className="muted">Nichts offen.</p>}
      {[...grouped.entries()].map(([kind, items]) => (
        <div key={kind} className="inbox-group">
          <h3>
            {KIND_LABEL[kind] ?? kind} <span className="muted">({items.length})</span>
          </h3>
          <ul>
            {items.map((a, i) => (
              <li key={i}>
                <span className="badge">{a.service}</span> {a.label} <span className="muted">{a.ref}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
