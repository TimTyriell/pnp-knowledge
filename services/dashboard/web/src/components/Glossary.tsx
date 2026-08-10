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

function stagedUnpin(edits: Edit[], cid: string): boolean {
  return edits.some((e) => e.op === "unpin" && e.concept_id === cid);
}

function stagedImportant(edits: Edit[], cid: string): boolean | undefined {
  for (let i = edits.length - 1; i >= 0; i--) {
    const e = edits[i];
    if (e.op === "set_important" && e.concept_id === cid) return e.important;
  }
  return undefined;
}

function stageRename(edits: Edit[], cid: string, name: string): Edit[] {
  // A new name replaces any staged unpin — renaming always (re)creates a pin.
  const rest = edits.filter((e) => !((e.op === "rename" || e.op === "unpin") && e.concept_id === cid));
  return [...rest, { op: "rename", concept_id: cid, name }];
}

function stageUnpin(edits: Edit[], cid: string): Edit[] {
  const rest = edits.filter((e) => !((e.op === "rename" || e.op === "unpin") && e.concept_id === cid));
  return [...rest, { op: "unpin", concept_id: cid }];
}

function unstageUnpin(edits: Edit[], cid: string): Edit[] {
  return edits.filter((e) => !(e.op === "unpin" && e.concept_id === cid));
}

function stageImportant(edits: Edit[], cid: string, important: boolean, original: boolean): Edit[] {
  const rest = edits.filter((e) => !(e.op === "set_important" && e.concept_id === cid));
  // Toggling back to the value it already had is a no-op — drop the edit
  // instead of staging a change that would produce an empty diff.
  if (important === original) return rest;
  return [...rest, { op: "set_important", concept_id: cid, important }];
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

  function handleTogglePin(cid: string, currentlyPinned: boolean, isStagedUnpin: boolean) {
    if (isStagedUnpin) {
      setEdits((eds) => unstageUnpin(eds, cid));
      return;
    }
    if (!currentlyPinned) return;
    setEdits((eds) => stageUnpin(eds, cid));
  }

  function handleToggleImportant(cid: string, effective: boolean, original: boolean) {
    setEdits((eds) => stageImportant(eds, cid, !effective, original));
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

      <details className="glossary-legend">
        <summary>
          Was bedeuten <span className="badge glossary-toggle">Pin</span> und <span className="badge glossary-toggle">★</span>?
        </summary>
        <dl>
          <dt>
            <span className="badge glossary-toggle">Pin</span>
          </dt>
          <dd>
            Der Anzeigename dieser Entität ist fest in <code>canonical_name:</code> (in <code>entity_rules.yaml</code>) hinterlegt. Ohne
            Pin nimmt die Pipeline bei jedem Lauf einfach die Schreibweise, die zuerst in einem Transkript auftaucht — eine Korrektur
            (z. B. „Slicks" → „Slix") würde sonst beim nächsten Lauf wieder verschwinden. Mit Pin bleibt sie stehen. Klick auf den Pin
            entfernt die Regel wieder; der Name fällt dann beim nächsten Lauf zurück auf das, was die Extraktion natürlich liefert.
          </dd>
          <dt>
            <span className="badge glossary-toggle">★</span>
          </dt>
          <dd>
            „Synthese" ist der Schritt, in dem die KI aus allen Erwähnungen einer Entität den eigentlichen Bundle-Text schreibt (der
            Fließtext in <code>knowledge/bundle/…</code>). Es gibt drei Tiefenstufen — <em>brief</em> (kurz), <em>standard</em>,{" "}
            <em>deep</em> (ausführlich, mit Rollen/Beziehungen/Chronologie) — normalerweise automatisch nach Erwähnungshäufigkeit und Typ
            vergeben. Der Stern erzwingt <em>deep</em> unabhängig davon — für Entitäten, die inhaltlich wichtig sind, aber
            selten/uneinheitlich erwähnt wurden (z. B. weil ihr Name mehrfach anders transkribiert wurde). Klick schaltet um; wirkt erst
            nach dem nächsten <code>pnp run</code>. Charaktere und Götter mit ≥2 Erwähnungen sind schon durch ihren Typ immer{" "}
            <em>deep</em> — bei denen zeigt der{" "}
            <span className="badge glossary-toggle-fixed" style={{ pointerEvents: "none" }}>
              ★
            </span>{" "}
            golden statt anklickbar, weil er dort nichts umschalten würde.
          </dd>
        </dl>
      </details>

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
              const unpinStaged = stagedUnpin(edits, cid);
              const adds = stagedAdds(edits, cid);
              const deletes = stagedDeletes(edits, cid);
              const deletedNames = new Set(deletes.map((d) => d.alias.toLowerCase()));
              const displayName = rename ?? e.canonical_name;
              const visibleAliases = e.aliases.filter((a) => !deletedNames.has(a.name.toLowerCase()));
              const effectivePinned = e.pinned && !unpinStaged;
              const stagedImp = stagedImportant(edits, cid);
              const effectiveImportant = stagedImp ?? e.important;
              const dirty = rename || unpinStaged || adds.length || deletes.length || stagedImp !== undefined;
              // Character/Deity with >=2 mentions are always deep-tier by
              // type alone (models.py ALWAYS_DEEP_TYPES) — the ★ toggle
              // would be a no-op for them, so show a fixed gold star instead
              // of a clickable one that lies about being optional.
              const alwaysDeep = (e.type === "Character" || e.type === "Deity") && e.mention_count >= 2;

              return (
                <tr key={cid} className={dirty ? "state-warn" : undefined}>
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
                    {(e.pinned || unpinStaged) && (
                      <button
                        className={`badge glossary-toggle${effectivePinned ? "" : " glossary-toggle-off"}`}
                        title={
                          effectivePinned
                            ? "Anzeigename per canonical_name: fixiert — klicken zum Entfernen"
                            : "Pin wird beim Sync entfernt — klicken zum Rückgängigmachen"
                        }
                        onClick={() => handleTogglePin(cid, e.pinned, unpinStaged)}
                      >
                        {effectivePinned ? "Pin" : "Pin ✗"}
                      </button>
                    )}
                    {alwaysDeep ? (
                      <span
                        className="badge glossary-toggle-fixed"
                        title="Charaktere und Götter sind ab 2 Erwähnungen immer tiefe Synthese — nicht abschaltbar"
                      >
                        ★
                      </span>
                    ) : (
                      <button
                        className={`badge glossary-toggle${effectiveImportant ? "" : " glossary-toggle-off"}`}
                        title={
                          effectiveImportant
                            ? "Erzwingt tiefe Synthese — klicken zum Ausschalten"
                            : "Klicken, um tiefe Synthese zu erzwingen"
                        }
                        onClick={() => handleToggleImportant(cid, effectiveImportant, e.important)}
                      >
                        ★
                      </button>
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
