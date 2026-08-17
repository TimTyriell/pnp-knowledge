import { useState } from "react";
import type { ServiceStatus } from "../types";

interface WikiRow {
  title: string;
  url: string;
  type: string;
  ki_last_edit: string;
  last_edit: string;
  last_editor: string;
  ki_state: "clean" | "edited" | "absent";
  anomalies: string[];
}

const STATE_LABEL: Record<string, string> = {
  clean: "unverändert",
  edited: "vom Team überarbeitet",
  absent: "kein KI-Abschnitt",
};

const STATE_CLASS: Record<string, string> = {
  clean: "state-ok",
  edited: "state-warn",
  absent: "state-bad",
};

type SortKey = "ki_last_edit" | "last_edit" | "title";

export function WikiTable({ exportStatus }: { exportStatus: ServiceStatus }) {
  const [sortKey, setSortKey] = useState<SortKey>("ki_last_edit");
  const rows = (exportStatus.items as unknown as WikiRow[] | undefined) ?? [];

  if (exportStatus.state === "missing") {
    return (
      <section className="panel">
        <h2>Wiki-Seiten</h2>
        <p className="muted">Noch keine Daten — `python 05_report.py` wurde in pnp-export-data noch nicht ausgeführt.</p>
      </section>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    if (sortKey === "title") return a.title.localeCompare(b.title);
    return (b[sortKey] ?? "").localeCompare(a[sortKey] ?? "");
  });

  return (
    <section className="panel">
      <h2>Wiki-Seiten ({rows.length})</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th onClick={() => setSortKey("title")} className="sortable">Seite</th>
              <th>Typ</th>
              <th onClick={() => setSortKey("ki_last_edit")} className="sortable">Letzte KI-Bearbeitung</th>
              <th onClick={() => setSortKey("last_edit")} className="sortable">Letzte Bearbeitung</th>
              <th>Von</th>
              <th>KI-Abschnitt</th>
              <th>Hinweise</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.title}>
                <td>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.title}
                  </a>
                </td>
                <td>{r.type || "—"}</td>
                <td>{r.ki_last_edit?.slice(0, 10) || "—"}</td>
                <td>{r.last_edit?.slice(0, 10) || "—"}</td>
                <td>{r.last_editor || "—"}</td>
                <td className={STATE_CLASS[r.ki_state]}>{STATE_LABEL[r.ki_state] ?? r.ki_state}</td>
                <td>{r.anomalies?.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
