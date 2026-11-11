import { useState } from "react";
import { postJson, useEpisodes, useSeasons } from "../useStatus";
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
  const seasonStatus = useSeasons();
  const [outputs, setOutputs] = useState<Record<string, string>>({});
  const [freezeErrors, setFreezeErrors] = useState<Record<string, string>>({});

  if (error) return <p className="error">Episodenliste nicht lesbar: {error}</p>;
  if (!data) return <p className="muted">Lade Folgen…</p>;
  if (data.error) return <p className="error">{data.error}</p>;

  const rows = new Map(funnel.filter((r) => r.video_id).map((r) => [r.video_id as string, r]));
  const statuses = new Map((seasonStatus.data?.seasons ?? []).map((season) => [season.key, season]));
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
      {seasonStatus.data?.unlisted_transcripts.length ? (
        <p className="cell-no">{seasonStatus.data.unlisted_transcripts.length} Transkript(e) ohne Eintrag in episodes.yaml — keiner Staffel zugeordnet.</p>
      ) : null}
      {seasonStatus.error && <p className="error">Staffelstatus nicht lesbar: {seasonStatus.error}</p>}
      {seasons.map(({ key, spec, eps }) => (
        <div key={key}>
          <h3>
            {spec.label} ({eps.length})
            {statuses.has(key) ? statuses.get(key)?.frozen ? (
              <>
                {" "}<span className="cell-yes">eingefroren seit {statuses.get(key)!.frozen!.frozen_at.slice(0, 10)} · extract v{statuses.get(key)!.frozen!.prompt_versions.extract}</span>
                {statuses.get(key)!.frozen!.prompt_versions.extract !== seasonStatus.data?.current.extract && <span className="cell-na"> (aktuell v{seasonStatus.data?.current.extract}, wird nicht neu gelesen)</span>}
              </>
            ) : (
              <>
                {" "}<span className="cell-no">aktiv</span>{" "}
                <button onClick={async () => {
                  if (!window.confirm("Staffel " + spec.label + " einfrieren? Kostet nichts; die Pipeline liest sie danach nicht mehr neu.")) return;
                  setFreezeErrors((old) => ({ ...old, [key]: "" }));
                  try {
                    const result = await postJson<{ output: string }>("/api/seasons/" + key + "/freeze", {});
                    setOutputs((old) => ({ ...old, [key]: result.output }));
                    seasonStatus.reload();
                    window.dispatchEvent(new Event("pnp-seasons-changed"));
                  } catch (err) {
                    setFreezeErrors((old) => ({ ...old, [key]: err instanceof Error ? err.message : String(err) }));
                  }
                }}>Einfrieren</button>
              </>
            ) : <span className="cell-na">Status nicht verfügbar</span>}
          </h3>
          {outputs[key] && <pre>{outputs[key]}</pre>}
          {freezeErrors[key] && <p className="error">{freezeErrors[key]}</p>}
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
