import { useEpisodes } from "../useStatus";
import type { Episode, FunnelRow } from "../types";

// Furthest stage the pipeline reached for this episode. An episode exists as
// soon as it is published, so "not downloaded yet" is a normal state here —
// unlike in the funnel, which only ever lists what pnp-crawl already knows.
function stage(row: FunnelRow | undefined): { label: string; className: string } {
  if (!row) return { label: "nicht geladen", className: "cell-na" };
  if (row.in_bundle) return { label: "im Bundle", className: "cell-yes" };
  if (row.exported) return { label: "exportiert", className: "cell-yes" };
  if (row.mapped) return { label: "Sprecher", className: "cell-no" };
  if (row.transcribed) return { label: "Transkript", className: "cell-no" };
  if (row.downloaded) return { label: "geladen", className: "cell-no" };
  return { label: "offen", className: "cell-na" };
}

function byDateDesc(a: Episode, b: Episode) {
  return String(b.date).localeCompare(String(a.date));
}

export function Episodes({ funnel }: { funnel: FunnelRow[] }) {
  const { data, error, loading, reload } = useEpisodes();

  if (error) return <p className="error">Episodenliste nicht lesbar: {error}</p>;
  if (!data) return <p className="muted">Lade Folgen…</p>;
  if (data.error) return <p className="error">{data.error}</p>;

  const rows = new Map(funnel.filter((r) => r.video_id).map((r) => [r.video_id as string, r]));
  const missingTitles = data.episodes.filter((ep) => !ep.title?.trim()).length;

  // Newest season first; a season with no episodes yet is not rendered.
  const seasons = Object.entries(data.seasons)
    .map(([key, spec]) => ({ key, spec, eps: data.episodes.filter((e) => String(e.season) === key) }))
    .filter((s) => s.eps.length > 0)
    .sort((a, b) => (b.eps[0].date ?? "").localeCompare(a.eps[0].date ?? ""));

  return (
    <section className="panel">
      <h2>
        Folgen ({data.episodes.length}){" "}
        {missingTitles > 0 && (
          <span className="cell-no" title="Abenteuername fehlt — wird für die Wikiseite gebraucht">
            · {missingTitles} ohne Namen
          </span>
        )}{" "}
        <button onClick={reload} disabled={loading}>
          {loading ? "…" : "Neu laden"}
        </button>
      </h2>
      {seasons.map(({ key, spec, eps }) => (
        <div key={key}>
          <h3>
            {spec.label} ({eps.length})
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Folge</th>
                  <th>Abenteuername</th>
                  <th>Beschreibung</th>
                  <th>Team</th>
                  <th>Datum</th>
                  <th>Status</th>
                  <th>Youtube</th>
                </tr>
              </thead>
              <tbody>
                {[...eps].sort(byDateDesc).map((ep) => {
                  const st = stage(rows.get(ep.video_id));
                  return (
                    <tr key={ep.video_id}>
                      <td className="cell-mono">{ep.id ?? "—"}</td>
                      <td>
                        {ep.title?.trim() || <span className="cell-no">TODO</span>}
                        {ep.tags?.map((t) => (
                          <span key={t} className="cell-mono">
                            {" "}
                            {t}
                          </span>
                        ))}
                      </td>
                      <td>{ep.description?.trim() || <span className="cell-na">—</span>}</td>
                      <td>{ep.team}</td>
                      <td>{ep.date}</td>
                      <td className={st.className}>{st.label}</td>
                      <td>
                        {ep.url ? (
                          <a href={ep.url} target="_blank" rel="noreferrer">
                            ▶
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
