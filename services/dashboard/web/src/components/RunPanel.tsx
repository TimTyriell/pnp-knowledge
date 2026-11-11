import { useCallback, useEffect, useState } from "react";
import { postJson, useSeasons } from "../useStatus";
import type { CommandResult, RunState } from "../types";

export function isPeak(date: Date): boolean {
  const day = date.getUTCDay();
  const hour = date.getUTCHours();
  return day >= 1 && day <= 5 && ((hour >= 1 && hour < 4) || (hour >= 6 && hour < 10));
}

export function RunPanel() {
  const { data: seasonData } = useSeasons();
  const [kind, setKind] = useState<"run" | "state">("run");
  const [thaw, setThaw] = useState<string[]>([]);
  const [estimate, setEstimate] = useState<CommandResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/runs/current");
      if (!response.ok) throw new Error(response.statusText);
      setRun((await response.json()) as RunState);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!run?.running) return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [run?.running, refresh]);

  function selectionChanged(nextKind: "run" | "state", nextThaw: string[]) {
    setKind(nextKind);
    setThaw(nextThaw);
    setEstimate(null);
    setConfirmed(false);
    setError(null);
  }

  async function getEstimate() {
    setError(null);
    setConfirmed(false);
    try {
      setEstimate(await postJson<CommandResult>("/api/runs/estimate", { kind, thaw }));
    } catch (err) {
      setEstimate(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function startRun() {
    setSubmitting(true);
    setError(null);
    try {
      await postJson<CommandResult>("/api/runs", { kind, thaw, confirm: true });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <h2>Pipeline</h2>
      <fieldset>
        <legend>Lauf</legend>
        <label><input type="radio" name="run-kind" checked={kind === "run"} onChange={() => selectionChanged("run", thaw)} /> Wissensbasis (pnp run)</label>
        <label><input type="radio" name="run-kind" checked={kind === "state"} onChange={() => selectionChanged("state", thaw)} /> Status-Pass (pnp state)</label>
      </fieldset>
      {(seasonData?.seasons ?? []).filter((season) => season.frozen).map((season) => (
        <label key={season.key}>
          <input type="checkbox" checked={thaw.includes(season.key)} onChange={(event) => selectionChanged(kind, event.target.checked ? [...thaw, season.key] : thaw.filter((key) => key !== season.key))} />
          {season.label} einmalig neu lesen
        </label>
      ))}
      <button onClick={() => void getEstimate()}>Kosten schätzen</button>
      {estimate && <pre>{estimate.output}</pre>}
      {isPeak(new Date()) ? <p className="cell-no">Jetzt Peak-Tarif: doppelter Preis.</p> : <p className="muted">Off-Peak.</p>}
      <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> Kosten gesehen</label>
      <button onClick={() => void startRun()} disabled={!estimate?.ok || !confirmed || !!run?.running || submitting}>Lauf starten</button>
      {error && <p className="error">{error}</p>}
      {run?.running && <><p className="muted">läuft seit {run.started_at}</p><pre>{run.log_tail}</pre></>}
      {run && !run.running && run.exit_code !== null && <p className={run.exit_code === 0 ? "cell-yes" : "cell-no"}>fertig (exit {run.exit_code})</p>}
    </section>
  );
}
