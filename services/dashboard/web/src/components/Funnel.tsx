import type { FunnelRow } from "../types";

function Check({ value }: { value: boolean | null }) {
  if (value === null) return <span className="cell-na">—</span>;
  return <span className={value ? "cell-yes" : "cell-no"}>{value ? "✓" : "·"}</span>;
}

export function Funnel({ rows }: { rows: FunnelRow[] }) {
  const sorted = [...rows].sort((a, b) => (b.video_date ?? "").localeCompare(a.video_date ?? ""));
  return (
    <section className="panel">
      <h2>Pipeline-Durchlauf</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Folge</th>
              <th>Datum</th>
              <th>Session</th>
              <th>DL</th>
              <th>Transkript</th>
              <th>Sprecher</th>
              <th>Export</th>
              <th>Im Bundle</th>
              <th>Lead-Time</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.video_id ?? r.video_date}>
                <td className="cell-mono" title={r.episode_title ?? undefined}>
                  {r.episode ?? "—"}
                </td>
                <td>{r.video_date ?? "—"}</td>
                <td className="cell-mono">{r.stem ?? r.video_id ?? "—"}</td>
                <td>
                  <Check value={r.downloaded} />
                </td>
                <td>
                  <Check value={r.transcribed} />
                </td>
                <td>
                  <Check value={r.mapped} />
                </td>
                <td>
                  <Check value={r.exported} />
                </td>
                <td>
                  <Check value={r.in_bundle} />
                </td>
                <td>{r.lead_time_days != null ? `${r.lead_time_days}d` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
