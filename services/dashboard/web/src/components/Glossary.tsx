import { useMemo, useState } from "react";
import { useGlossary } from "../useStatus";
import type { AliasSource, Edit, GlossaryAlias, GlossaryEntity, SyncPreview } from "../types";

type SortKey = "canonical_name" | "total_count" | "mention_count";

const SOURCE_LABEL: Record<AliasSource, string> = {
  canonical: "Hauptname",
  merge: "Regel (merge:)",
  registry: "aus der Extraktion",
};

function matches(e: GlossaryEntity, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  if (e.canonical_name.toLowerCase().includes(needle)) return true;
  if (e.concept_id.toLowerCase().includes(needle)) return true;
  return e.aliases.some((a) => a.name.toLowerCase().includes(needle));
}

function stagedRename(edits: Edit[], cid: string): string | undefined {
  for (let i = edits.length - 1; i >= 0; i--) {
    const e = edits[i];
    if (e.op === "rename" && e.concept_id === cid) return e.name;
  }
  return undefined;
}

function stagedAdds(edits: Edit[], cid: string): string[] {
  return edits.filter((e): e is Extract<Edit, { op: "add_alias" }> => e.op === "add_alias" && e.concept_id === cid).map((e) => e.alias);
}

function stagedDeletes(edits: Edit[], cid: string): Extract<Edit, { op: "delete_alias" }>[] {
  return edits.filter((e): e is Extract<Edit, { op: "delete_alias" }> => e.op === "delete_alias" && e.concept_id === cid);
}

function stageRename(edits: Edit[], cid: string, name: string): Edit[] {
  const rest = edits.filter((e) => !(e.op === "rename" && e.concept_id === cid));
  return [...rest, { op: "rename", concept_id: cid, name }];
}

function stageAddAlias(edits: Edit[], cid: string, alias: string): Edit[] {
  const key = alias.toLowerCase();
  // Re-adding something staged for deletion just cancels the deletion.
  const withoutDelete = edits.filter((e) => !(e.op === "delete_alias" && e.concept_id === cid && e.alias.toLowerCase() === key));
  if (withoutDelete.length !== edits.length) return withoutDelete;
  if (edits.some((e) => e.op === "add_alias" && e.concept_id === cid && e.alias.toLowerCase() === key)) return edits;
  return [...edits, { op: "add_alias", concept_id: cid, alias }];
}

function stageDeleteAlias(edits: Edit[], cid: string, alias: string, source: AliasSource, unfoldAck?: boolean): Edit[] {
  const key = alias.toLowerCase();
  // Deleting something that was only a staged add just drops the add.
  const withoutAdd = edits.filter((e) => !(e.op === "add_alias" && e.concept_id === cid && e.alias.toLowerCase() === key));
  if (withoutAdd.length !== edits.length) return withoutAdd;
  const rest = edits.filter((e) => !(e.op === "delete_alias" && e.concept_id === cid && e.alias.toLowerCase() === key));
  return [...rest, { op: "delete_alias", concept_id: cid, alias, source, unfold_ack: unfoldAck }];
}

function unstageDelete(edits: Edit[], cid: string, alias: string): Edit[] {
  const key = alias.toLowerCase();
  return edits.filter((e) => !(e.op === "delete_alias" && e.concept_id === cid && e.alias.toLowerCase() === key));
}

async function postEdits(edits: Edit[], dryRun: boolean): Promise<SyncPreview> {
  const res = await fetch("/api/glossary/edits", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: dryRun, edits }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as { detail?: string });
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SyncPreview;
}

export function Glossary() {
  const { data, error, loading, reload } = useGlossary();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("total_count");
  const [edits, setEdits] = useState<Edit[]>([]);
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => {
    if (!data) return [];
    let out = data.entities;
    if (type) out = out.filter((e) => e.type === type);
    if (q) out = out.filter((e) => matches(e, q));
    return [...out].sort((a, b) => {
      if (sortKey === "canonical_name") return a.canonical_name.localeCompare(b.canonical_name);
      return b[sortKey] - a[sortKey];
    });
  }, [data, type, q, sortKey]);

  function handleDeleteAlias(cid: string, a: GlossaryAlias) {
    if (a.source === "canonical") return;
    if (a.source === "merge") {
      const unfold = window.confirm(
        `"${a.name}" ist eine merge-Regel. Beim nächsten Pipeline-Lauf bilden alle Erwähnungen von ` +
          `"${a.name}" ein eigenes Konzept, statt zu diesem Eintrag zu gehören — das ist eine ` +
          `Identitätsänderung, keine Kosmetik.\n\n` +
          `OK = Regel löschen (Identität ändert sich)\n` +
          `Abbrechen = nur ausblenden (Regel bleibt bestehen, Schreibweise verschwindet nur aus der Anzeige)`
      );
      setEdits((eds) => stageDeleteAlias(eds, cid, a.name, "merge", unfold));
      return;
    }
    setEdits((eds) => stageDeleteAlias(eds, cid, a.name, "registry"));
  }

  function handleAddAlias(cid: string, value: string) {
    const alias = value.trim();
    if (!alias) return;
    setEdits((eds) => stageAddAlias(eds, cid, alias));
  }

  async function handlePreview() {
    setSyncError(null);
    setBusy(true);
    try {
      setPreview(await postEdits(edits, true));
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleWrite() {
    setSyncError(null);
    setBusy(true);
    try {
      await postEdits(edits, false);
      setEdits([]);
      setPreview(null);
      reload();
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function handleDiscard() {
    setEdits([]);
    setPreview(null);
    setSyncError(null);
  }

  if (!data && !error) {
    return (
      <section className="panel">
        <h2>Glossar</h2>
        <p className="muted">Lade Glossar… (erste Zählung über alle Transkripte dauert ein paar Sekunden)</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel">
        <h2>Glossar</h2>
        <p className="error">Glossar-API nicht erreichbar: {error}</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>
        Glossar ({rows.length}/{data.entities.length})
        {data.stale && <span className="badge state-warn glossary-stale-badge">Bundle veraltet</span>}
        {loading && <span className="muted glossary-loading"> aktualisiere…</span>}
      </h2>
      {data.stale && (
        <p className="muted">
          Regeln wurden nach dem letzten Bundle-Lauf geändert. Um Titel/Aliase im Bundle zu übernehmen: <code>pnp run</code> in{" "}
          <code>services/kb</code> ausführen.
        </p>
      )}
      <div className="glossary-filters">
        <input type="search" placeholder="Suche Name, Alias oder ID…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Alle Typen</option>
          {data.types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button onClick={reload} disabled={loading}>
          Neu laden
        </button>
      </div>

      {edits.length > 0 && (
        <div className="glossary-sync-bar">
          <span>{edits.length} geänderte Regel(n) noch nicht synchronisiert.</span>
          <button onClick={handlePreview} disabled={busy}>
            Synchronisieren
          </button>
          <button onClick={handleDiscard} disabled={busy}>
            Verwerfen
          </button>
        </div>
      )}
      {syncError && <p className="error">{syncError}</p>}
      {preview && (
        <div className="glossary-preview panel">
          {preview.warnings.length > 0 && (
            <ul className="glossary-warnings">
              {preview.warnings.map((w, i) => (
                <li key={i} className="state-warn">
                  {w}
                </li>
              ))}
            </ul>
          )}
          {preview.diff ? (
            <pre className="glossary-diff">{preview.diff}</pre>
          ) : (
            <p className="muted">Keine Änderungen gegenüber der aktuellen Datei.</p>
          )}
          <div className="glossary-sync-bar">
            <button onClick={handleWrite} disabled={busy || !preview.diff}>
              Schreiben
            </button>
            <button onClick={() => setPreview(null)} disabled={busy}>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th onClick={() => setSortKey("canonical_name")} className="sortable">
                Name
              </th>
              <th>Typ</th>
              <th>Aliase</th>
              <th onClick={() => setSortKey("total_count")} className="sortable">
                Σ Vorkommen
              </th>
              <th onClick={() => setSortKey("mention_count")} className="sortable">
                Sessions
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => {
              const cid = e.concept_id;
              const rename = stagedRename(edits, cid);
              const adds = stagedAdds(edits, cid);
              const deletes = stagedDeletes(edits, cid);
              const deletedNames = new Set(deletes.map((d) => d.alias.toLowerCase()));
              const displayName = rename ?? e.canonical_name;
              const visibleAliases = e.aliases.filter((a) => !deletedNames.has(a.name.toLowerCase()));

              return (
                <tr key={cid} className={rename || adds.length || deletes.length ? "state-warn" : undefined}>
                  <td>
                    <input
                      key={`${cid}-${displayName}`}
                      className="glossary-name-input"
                      defaultValue={displayName}
                      onBlur={(ev) => {
                        const v = ev.target.value.trim();
                        if (v && v !== e.canonical_name) setEdits((eds) => stageRename(eds, cid, v));
                        else if (v === e.canonical_name) setEdits((eds) => eds.filter((x) => !(x.op === "rename" && x.concept_id === cid)));
                      }}
                      onKeyDown={(ev) => {
                        if (ev.key === "Enter") (ev.target as HTMLInputElement).blur();
                      }}
                    />
                    {e.pinned && (
                      <span className="badge" title="Anzeigename per canonical_name: fixiert">
                        Pin
                      </span>
                    )}
                    {e.important && (
                      <span className="badge" title="Erzwingt tiefe Synthese">
                        ★
                      </span>
                    )}
                  </td>
                  <td>{e.type}</td>
                  <td>
                    <div className="chip-row">
                      {visibleAliases.map((a) => (
                        <span key={a.name} className="chip" title={SOURCE_LABEL[a.source]}>
                          {a.name} <span className="badge">{a.count}</span>
                          {a.source !== "canonical" && (
                            <button className="chip-remove" onClick={() => handleDeleteAlias(cid, a)} aria-label={`"${a.name}" löschen`}>
                              ×
                            </button>
                          )}
                        </span>
                      ))}
                      {adds.map((name) => (
                        <span key={name} className="chip glossary-chip-pending" title="Neu, noch nicht synchronisiert">
                          {name}
                          <button
                            className="chip-remove"
                            onClick={() => setEdits((eds) => eds.filter((x) => !(x.op === "add_alias" && x.concept_id === cid && x.alias === name)))}
                            aria-label={`"${name}" verwerfen`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {deletes.map((d) => (
                        <span
                          key={d.alias}
                          className="chip glossary-chip-deleted"
                          title="Wird beim Sync entfernt — klicken zum Rückgängigmachen"
                          onClick={() => setEdits((eds) => unstageDelete(eds, cid, d.alias))}
                        >
                          {d.alias}
                        </span>
                      ))}
                      <input
                        className="glossary-add-alias"
                        placeholder="+ Alias"
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter") {
                            handleAddAlias(cid, (ev.target as HTMLInputElement).value);
                            (ev.target as HTMLInputElement).value = "";
                          }
                        }}
                      />
                    </div>
                  </td>
                  <td>{e.total_count}</td>
                  <td>{e.mention_count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
