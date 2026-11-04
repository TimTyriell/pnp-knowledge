import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import ReactMarkdown from "react-markdown";
import {
  BookOpen,
  Clock3,
  Download,
  FileText,
  LayoutDashboard,
  Plus,
  Search,
  Upload,
  Users,
} from "lucide-react";
import Dashboard from "./Dashboard";
import {
  api,
  type Campaign,
  type Entry,
  type Proposal,
  type Workspace,
} from "./workbench";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type View = "knowledge" | "sources" | "review" | "history" | "dashboard";
type Draft = {
  title: string;
  type: string;
  body: string;
  aliases: string;
  related: string[];
  baseRevision: string;
};
type SourceDraft = {
  title: string;
  date: string;
  text: string;
  fileName: string;
};
type DraftStore = {
  drafts: Record<string, Draft>;
  put: (key: string, draft: Draft) => void;
  clear: (key: string) => void;
};
const useDrafts = create<DraftStore>()(
  persist(
    (set) => ({
      drafts: {},
      put: (key, draft) =>
        set((state) => ({ drafts: { ...state.drafts, [key]: draft } })),
      clear: (key) =>
        set((state) => {
          const drafts = { ...state.drafts };
          delete drafts[key];
          return { drafts };
        }),
    }),
    { name: "campaign-workbench-drafts" },
  ),
);
const useSourceDrafts = create<{
  drafts: Record<string, SourceDraft>;
  put: (key: string, draft: SourceDraft) => void;
  clear: (key: string) => void;
}>()(
  persist(
    (set) => ({
      drafts: {},
      put: (key, draft) =>
        set((state) => ({ drafts: { ...state.drafts, [key]: draft } })),
      clear: (key) =>
        set((state) => {
          const drafts = { ...state.drafts };
          delete drafts[key];
          return { drafts };
        }),
    }),
    { name: "campaign-workbench-source-drafts" },
  ),
);

const types = [
  "Character",
  "NPC",
  "Location",
  "Faction",
  "Item",
  "Event",
  "Deity",
  "Domain",
];
const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
const keyFor = (workspace: string, entry: string) => `${workspace}:${entry}`;

export default function App() {
  const client = useQueryClient();
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [view, setView] = useState<View>("knowledge");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [entryId, setEntryId] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);
  const shouldRevealSelection = useRef(false);
  const [editing, setEditing] = useState(false);
  const activeEditor = useRef<{
    campaignId: string | null;
    entryId: string | null;
  }>({ campaignId, entryId });
  activeEditor.current = { campaignId, entryId };
  const list = useQuery({ queryKey: ["workspaces"], queryFn: api.list });
  const config = useQuery({
    queryKey: ["workbench-config"],
    queryFn: api.config,
  });
  const campaign = useQuery({
    queryKey: ["workspace", campaignId],
    queryFn: () => api.workspace(campaignId!),
    enabled: !!campaignId,
    refetchInterval: (query) =>
      query.state.data?.jobs?.some((job) => job.status === "running")
        ? 1500
        : false,
  });
  const invalidate = async (workspace: Workspace) => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["workspaces"] }),
      client.setQueryData(["workspace", workspace.id], workspace),
    ]);
  };
  const createCampaign = useMutation({
    mutationFn: ({
      name,
      description,
    }: {
      name: string;
      description: string;
    }) => api.create(name, description),
    onSuccess: async (result) => {
      await invalidate(result);
      setCampaignId(result.id);
    },
  });
  const importCampaign = useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) =>
      api.importBundle(name, file),
    onSuccess: async (result) => {
      await invalidate(result);
      setCampaignId(result.id);
    },
  });
  const saveEntry = useMutation({
    mutationFn: ({
      draft,
      id,
      revision,
      concept,
    }: {
      draft: Draft;
      id: string;
      revision: string;
      concept?: string;
    }) =>
      api.saveEntry(
        id,
        {
          title: draft.title,
          type: draft.type,
          body: draft.body,
          aliases: draft.aliases
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          related: draft.related,
        },
        revision,
        concept,
      ),
    onSuccess: async (result, variables) => {
      await invalidate(result);
      useDrafts
        .getState()
        .clear(keyFor(variables.id, variables.concept ?? "new"));
      if (
        activeEditor.current.campaignId === variables.id &&
        activeEditor.current.entryId === (variables.concept ?? "new")
      ) {
        setEntryId(null);
        setEditing(false);
      }
    },
    onError: async (_error, variables) => {
      await client.invalidateQueries({ queryKey: ["workspace", variables.id] });
    },
  });
  const addSource = useMutation({
    mutationFn: ({
      id,
      source,
    }: {
      id: string;
      source: { title: string; date: string; text: string };
    }) => api.addSource(id, source),
    onSuccess: invalidate,
  });
  const processSource = useMutation({
    mutationFn: ({ id, sourceId }: { id: string; sourceId: string }) =>
      api.processSource(id, sourceId),
    onSuccess: invalidate,
  });
  const review = useMutation({
    mutationFn: ({
      id,
      revision,
      decisions,
    }: {
      id: string;
      revision: string;
      decisions: {
        id: string;
        action: "accept" | "reject";
        target?: string | null;
        body?: string;
      }[];
    }) => api.review(id, revision, decisions),
    onSuccess: invalidate,
  });
  const restore = useMutation({
    mutationFn: ({
      id,
      revision,
      target,
    }: {
      id: string;
      revision: string;
      target: string;
    }) => api.restore(id, revision, target),
    onSuccess: invalidate,
  });

  useEffect(() => {
    const hasSelectedEntry =
      campaign.data?.entries.some((entry) => entry.concept === entryId) ??
      false;
    if (
      !shouldRevealSelection.current ||
      view !== "knowledge" ||
      !hasSelectedEntry
    )
      return;
    shouldRevealSelection.current = false;
    if (window.innerWidth > 760 || !detailRef.current) return;

    const title = detailRef.current.querySelector('[data-slot="card-title"]');
    const bounds = title?.getBoundingClientRect();
    if (!bounds || bounds.top < 0 || bounds.bottom > window.innerHeight) {
      detailRef.current.scrollIntoView({ block: "start" });
    }
  }, [campaign.data, entryId, view]);

  if (view === "dashboard")
    return (
      <div className="legacy-shell">
        <button className="back-workbench" onClick={() => setView("knowledge")}>
          ← Campaign workbench
        </button>
        <Dashboard />
      </div>
    );
  if (!campaignId)
    return (
      <StartPage
        campaigns={list.data ?? []}
        loading={list.isLoading}
        error={list.error ? message(list.error) : null}
        onOpen={(id) => setCampaignId(id)}
        onCreate={(name, description) =>
          createCampaign.mutate({ name, description })
        }
        onImport={(name, file) => importCampaign.mutate({ name, file })}
        onDashboard={() => setView("dashboard")}
        busy={createCampaign.isPending || importCampaign.isPending}
        errorMessage={
          createCampaign.error
            ? message(createCampaign.error)
            : importCampaign.error
              ? message(importCampaign.error)
              : null
        }
      />
    );
  if (!campaign.data)
    return (
      <main className="workbench-shell">
        <Button variant="ghost" onClick={() => setCampaignId(null)}>
          ← All campaigns
        </Button>
        <p role="status">
          {campaign.error
            ? `Could not load campaign: ${message(campaign.error)}`
            : "Loading campaign…"}
        </p>
        <Button variant="outline" onClick={() => void campaign.refetch()}>
          Try again
        </Button>
      </main>
    );

  const data = campaign.data;
  const selected =
    data.entries.find((entry) => entry.concept === entryId) ?? null;
  const filteredEntries = data.entries.filter(
    (entry) =>
      (typeFilter === "all" || entry.type === typeFilter) &&
      `${entry.title} ${entry.aliases.join(" ")} ${entry.body}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const pending = data.proposals.filter(
    (proposal) => proposal.status === "pending",
  );
  const safeBulk = pending.filter(
    (proposal) => !proposal.needs_decision && !proposal.target,
  );
  const navigateToEntry = (concept: string) => {
    shouldRevealSelection.current = true;
    setView("knowledge");
    setEntryId(concept);
    setEditing(false);
  };

  async function exportBundle() {
    try {
      const blob = await api.export(data.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${data.name.replace(/[^\w.-]+/g, "-")}-campaign.zip`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      window.alert(message(error));
    }
  }

  return (
    <main className="workbench-shell">
      <header className="wb-header">
        <div>
          <Button
            variant="ghost"
            onClick={() => {
              setCampaignId(null);
              setEntryId(null);
              setEditing(false);
            }}
          >
            ← All campaigns
          </Button>
          <p className="eyebrow">Campaign workbench</p>
          <h1>{data.name}</h1>
          {data.description && <p className="subtle">{data.description}</p>}
        </div>
        <div className="header-actions">
          <Button variant="outline" onClick={() => setView("dashboard")}>
            <LayoutDashboard /> Technical dashboard
          </Button>
          <Button onClick={() => void exportBundle()}>
            <Download /> Export bundle
          </Button>
        </div>
      </header>
      <nav className="workbench-nav" aria-label="Campaign sections">
        {(
          [
            ["knowledge", "Knowledge", BookOpen, data.entries.length],
            ["sources", "Sources", FileText, data.sources.length],
            ["review", "Review", Users, pending.length],
            ["history", "History", Clock3, data.history.length],
          ] as const
        ).map(([key, label, Icon, count]) => (
          <button
            key={key}
            className={view === key ? "selected" : ""}
            onClick={() => {
              setView(key);
              setEntryId(null);
              setEditing(false);
            }}
          >
            <Icon aria-hidden="true" />
            {label}
            <Badge variant="secondary">{count}</Badge>
          </button>
        ))}
      </nav>
      {view === "knowledge" && (
        <section className="knowledge-layout">
          <Card className="entry-list">
            <CardHeader>
              <CardTitle>Campaign knowledge</CardTitle>
              <CardDescription>
                Keep the people, places, and details of your world together.
              </CardDescription>
              <div className="filter-row">
                <label className="search-box">
                  <Search aria-hidden="true" />
                  <Input
                    aria-label="Search entries"
                    placeholder="Search names and notes"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </label>
                <select
                  aria-label="Filter by type"
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                >
                  <option value="all">All types</option>
                  {[...new Set(data.entries.map((entry) => entry.type))].map(
                    (type) => (
                      <option key={type}>{type}</option>
                    ),
                  )}
                </select>
              </div>
            </CardHeader>
            <CardContent>
              <Button
                className="new-entry"
                onClick={() => {
                  setEntryId("new");
                  setEditing(true);
                }}
              >
                <Plus /> Add an entry
              </Button>
              {filteredEntries.length ? (
                <ul className="entry-list-items">
                  {filteredEntries.map((entry) => (
                    <li key={entry.concept}>
                      <button
                        className={entryId === entry.concept ? "active" : ""}
                        onClick={() => navigateToEntry(entry.concept)}
                      >
                        <span>{entry.title}</span>
                        <Badge variant="outline">{entry.type}</Badge>
                        <small>
                          {entry.aliases.length
                            ? entry.aliases.join(", ")
                            : entry.concept}
                        </small>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-note">
                  {data.entries.length
                    ? "No entries match this search."
                    : "Your campaign starts here. Add your first character, place, or detail."}
                </p>
              )}
            </CardContent>
          </Card>
          <Card ref={detailRef} className="entry-detail">
            {entryId ? (
              <EntryPanel
                key={entryId}
                workspace={data}
                entry={selected}
                onNavigate={navigateToEntry}
                editing={editing}
                onEdit={() => setEditing(true)}
                onCancel={() => {
                  setEditing(false);
                  if (entryId === "new") setEntryId(null);
                }}
                onSave={(draft, revision) =>
                  saveEntry.mutate({
                    draft,
                    id: data.id,
                    revision,
                    concept: selected?.concept,
                  })
                }
                saving={saveEntry.isPending}
                error={saveEntry.error ? message(saveEntry.error) : null}
              />
            ) : (
              <div className="welcome-panel">
                <BookOpen />
                <h2>Select an entry</h2>
                <p>
                  Choose something from the list, or add a new piece of
                  campaign knowledge.
                </p>
                <Button
                  onClick={() => {
                    setEntryId("new");
                    setEditing(true);
                  }}
                >
                  <Plus /> Add an entry
                </Button>
              </div>
            )}
          </Card>
        </section>
      )}
      {view === "sources" && (
        <SourcesPanel
          workspace={data}
          aiAvailable={config.data?.ai_available ?? false}
          model={config.data?.model ?? null}
          maxChars={config.data?.max_source_chars ?? 120000}
          onAdd={async (source) => {
            await addSource.mutateAsync({ id: data.id, source });
          }}
          onProcess={(sourceId) =>
            processSource.mutate({ id: data.id, sourceId })
          }
          busy={addSource.isPending || processSource.isPending}
          error={
            addSource.error
              ? message(addSource.error)
              : processSource.error
                ? message(processSource.error)
                : null
          }
        />
      )}
      {view === "review" && (
        <ReviewPanel
          workspace={data}
          onNavigate={navigateToEntry}
          pending={pending}
          safeBulk={safeBulk}
          onApply={(decisions) =>
            review.mutate({ id: data.id, revision: data.revision, decisions })
          }
          busy={review.isPending}
          error={review.error ? message(review.error) : null}
        />
      )}
      {view === "history" && (
        <HistoryPanel
          workspace={data}
          onRestore={(target) =>
            restore.mutate({ id: data.id, revision: data.revision, target })
          }
          busy={restore.isPending}
          error={restore.error ? message(restore.error) : null}
        />
      )}
      <footer className="workbench-footer">
        Saved version <code>{data.revision.slice(0, 8)}</code> ·{" "}
        {data.entries.length} entries
        {campaign.isFetching && <span role="status"> · Syncing…</span>}
      </footer>
    </main>
  );
}

function StartPage({
  campaigns,
  loading,
  error,
  onOpen,
  onCreate,
  onImport,
  onDashboard,
  busy,
  errorMessage,
}: {
  campaigns: Campaign[];
  loading: boolean;
  error: string | null;
  onOpen: (id: string) => void;
  onCreate: (name: string, description: string) => void;
  onImport: (name: string, file: File) => void;
  onDashboard: () => void;
  busy: boolean;
  errorMessage: string | null;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [importName, setImportName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  return (
    <main className="start-shell">
      <header className="start-brand">
        <div className="brand-mark">
          <BookOpen />
        </div>
        <div>
          <p className="eyebrow">Your tabletop campaign</p>
          <h1>Campaign workbench</h1>
        </div>
        <Button
          variant="outline"
          className="start-dashboard"
          onClick={onDashboard}
        >
          <LayoutDashboard /> Technical dashboard
        </Button>
      </header>
      <p className="start-intro">
        Build a clear, searchable memory of your world. Create a campaign or
        continue one saved on this computer.
      </p>
      {errorMessage && (
        <p className="error-banner" role="alert">
          {errorMessage}
        </p>
      )}
      {error && (
        <p className="error-banner" role="alert">
          Campaign list could not load: {error}{" "}
          <Button variant="outline" onClick={() => location.reload()}>
            Retry
          </Button>
        </p>
      )}
      <div className="start-grid">
        <Card>
          <CardHeader>
            <CardTitle>Create a campaign</CardTitle>
            <CardDescription>
              Start with a name. Add your world’s details whenever you’re ready.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="stack-form"
              onSubmit={(event) => {
                event.preventDefault();
                onCreate(name.trim(), description.trim());
              }}
            >
              <label htmlFor="campaign-name">Campaign name</label>
              <Input
                id="campaign-name"
                required
                maxLength={120}
                placeholder="The Shattered Isles"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <label htmlFor="campaign-description">
                Short description <span className="subtle">(optional)</span>
              </label>
              <Textarea
                id="campaign-description"
                maxLength={2000}
                rows={3}
                placeholder="A few words to help you recognize this world"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <Button type="submit" disabled={busy || !name.trim()}>
                <Plus /> Create campaign
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Open a campaign bundle</CardTitle>
            <CardDescription>
              Bring in a compatible ZIP bundle. Your import opens in a new
              workspace.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="stack-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (file)
                  onImport(
                    importName.trim() || file.name.replace(/\.zip$/i, ""),
                    file,
                  );
              }}
            >
              <label htmlFor="import-name">Campaign name</label>
              <Input
                id="import-name"
                required
                value={importName}
                onChange={(event) => setImportName(event.target.value)}
                placeholder="Name this campaign"
              />
              <label htmlFor="bundle-file">Choose a campaign bundle ZIP</label>
              <Input
                id="bundle-file"
                type="file"
                accept=".zip,application/zip"
                required
                onChange={(event) => {
                  const picked = event.target.files?.[0] ?? null;
                  setFile(picked);
                  if (picked && !importName)
                    setImportName(picked.name.replace(/\.zip$/i, ""));
                }}
              />
              <p className="hint">
                ZIP files up to 25 MB. Your original file is not changed.
              </p>
              <Button type="submit" variant="outline" disabled={busy || !file}>
                <Upload /> Import campaign
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
      <section className="saved-campaigns">
        <h2>Saved on this computer</h2>
        {loading ? (
          <p role="status">Loading your campaigns…</p>
        ) : campaigns.length ? (
          <ul>
            {campaigns.map((campaign) => (
              <li key={campaign.id}>
                <button onClick={() => onOpen(campaign.id)}>
                  <span>
                    <strong>{campaign.name}</strong>
                    <small>
                      {campaign.entry_count} entries ·{" "}
                      {campaign.description || "Campaign workspace"}
                    </small>
                  </span>
                  <span aria-hidden="true">→</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-note">
            No campaigns yet. Your work stays on this computer.
          </p>
        )}
      </section>
    </main>
  );
}

function linkedConcept(
  sourceConcept: string,
  href: string | undefined,
  entries: Entry[],
): string | null {
  if (
    !href ||
    href.startsWith("#") ||
    href.startsWith("//") ||
    /^[a-z][a-z\d+.-]*:/i.test(href)
  )
    return null;

  const rawPath = href.split(/[?#]/, 1)[0] ?? "";
  const targetFromUrl = (url: URL, origin: string) => {
    if (url.origin !== origin) return null;
    let decoded: string;
    try {
      decoded = decodeURIComponent(url.pathname).replace(/\\/g, "/");
    } catch {
      return null;
    }
    const conceptPath = decoded
      .replace(/^\/+/, "")
      .replace(/\.md$/i, "")
      .replace(/\/+$/, "");
    return entries.find((entry) => entry.concept === conceptPath)?.concept ?? null;
  };

  try {
    const root = new URL("https://workbench.invalid/");
    const isRelativeTraversal = rawPath.startsWith("./") || rawPath.startsWith("../");
    if (!isRelativeTraversal) {
      const rootTarget = targetFromUrl(new URL(rawPath, root), root.origin);
      if (rootTarget) return rootTarget;
    }
    const base = new URL(`${sourceConcept}.md`, root);
    return targetFromUrl(new URL(rawPath, base), root.origin);
  } catch {
    return null;
  }
}

function EntryMarkdown({
  sourceConcept,
  workspace,
  onNavigate,
  children,
}: {
  sourceConcept: string;
  workspace: Workspace;
  onNavigate: (concept: string) => void;
  children: string;
}) {
  return (
    <ReactMarkdown
      components={{
        a: ({ href, children: linkChildren, node, ...props }) => {
          void node;
          const target = linkedConcept(
            sourceConcept,
            href,
            workspace.entries,
          );
          return (
            <a
              {...props}
              href={href}
              onClick={(event) => {
                props.onClick?.(event);
                if (target && !event.defaultPrevented) {
                  event.preventDefault();
                  onNavigate(target);
                }
              }}
            >
              {linkChildren}
            </a>
          );
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

function EntryPanel({
  workspace,
  entry,
  onNavigate,
  editing,
  onEdit,
  onCancel,
  onSave,
  saving,
  error,
}: {
  workspace: Workspace;
  entry: Entry | null;
  onNavigate: (concept: string) => void;
  editing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (draft: Draft, revision: string) => void;
  saving: boolean;
  error: string | null;
}) {
  const entryKey = entry?.concept ?? "new";
  const draftKey = keyFor(workspace.id, entryKey);
  const storedDraft = useDrafts((state) => state.drafts[draftKey]);
  const initial: Draft = storedDraft ?? {
    title: entry?.title ?? "",
    type: entry?.type ?? "NPC",
    body: entry?.body ?? "",
    aliases: entry?.aliases.join(", ") ?? "",
    related: entry?.related ?? [],
    baseRevision: workspace.revision,
  };
  const [draft, setDraft] = useState<Draft>(initial);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const saveDraft = (next: Draft) => {
    setDraft(next);
    useDrafts.getState().put(draftKey, next);
  };
  const formatBody = (format: "bold" | "heading" | "list") => {
    const body = draft.body;
    const selectionStart = bodyRef.current?.selectionStart ?? 0;
    const selectionEnd = bodyRef.current?.selectionEnd ?? 0;
    const start = selectionStart === selectionEnd ? 0 : selectionStart;
    const end = selectionStart === selectionEnd ? body.length : selectionEnd;
    const selected = start === end ? "Text" : body.slice(start, end);
    let replacement = selected;
    if (format === "bold") replacement = `**${selected}**`;
    if (format === "heading")
      replacement = selected
        .split("\n")
        .map((line) => `## ${line.replace(/^#+\s*/, "")}`)
        .join("\n");
    if (format === "list")
      replacement = selected
        .split("\n")
        .map((line) => `- ${line.replace(/^-\s*/, "")}`)
        .join("\n");
    const next = `${body.slice(0, start)}${replacement}${body.slice(end)}`;
    saveDraft({ ...draft, body: next });
    requestAnimationFrame(() => {
      bodyRef.current?.focus();
      bodyRef.current?.setSelectionRange(start, start + replacement.length);
    });
  };
  const outOfDate = draft.baseRevision !== workspace.revision;
  const [preview, setPreview] = useState(false);
  if (!editing || (entry !== null && !entry.editable))
    return (
      <>
        <CardHeader>
          <div className="detail-title">
            <div>
              <Badge variant="outline">{entry?.type}</Badge>
              <CardTitle>{entry?.title}</CardTitle>
            </div>
            {entry?.editable && (
              <Button variant="outline" onClick={onEdit}>
                Edit entry
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {entry && !entry.editable && (
            <p className="read-only-note" role="status">
              Imported {entry.type} content is read-only in the workbench. It remains available here and in exported bundles.
            </p>
          )}
          <div className="entry-meta">
            <strong>Aliases</strong>
            <span>
              {entry?.aliases.length ? entry.aliases.join(", ") : "No aliases"}
            </span>
          </div>
          <h3>Description and notes</h3>
          <div className="markdown-preview">
            {entry && (
              <EntryMarkdown
                sourceConcept={entry.concept}
                workspace={workspace}
                onNavigate={onNavigate}
              >
                {entry.body || "*No description yet.*"}
              </EntryMarkdown>
            )}
          </div>
          <h3>Connected entries</h3>
          <div className="related-list">
            {entry?.related.length ? (
              entry.related.map((id) => {
                const related = workspace.entries.find(
                  (row) => row.concept === id,
                );
                return (
                  <Badge key={id} variant="secondary">
                    {related?.title ?? id}
                  </Badge>
                );
              })
            ) : (
              <span className="subtle">No connections yet</span>
            )}
          </div>
        </CardContent>
      </>
    );
  return (
    <>
      <CardHeader>
        <CardTitle>
          {entry ? `Edit ${entry.title}` : "Add campaign entry"}
        </CardTitle>
        <CardDescription>
          Names and connections are easy to change later.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="stack-form editor-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSave(draft, draft.baseRevision);
          }}
        >
          <label htmlFor="entry-title">Name</label>
          <Input
            id="entry-title"
            required
            maxLength={200}
            value={draft.title}
            onChange={(event) =>
              saveDraft({ ...draft, title: event.target.value })
            }
          />
          <label htmlFor="entry-type">Type</label>
          <select
            id="entry-type"
            value={draft.type}
            disabled={!!entry}
            onChange={(event) =>
              saveDraft({ ...draft, type: event.target.value })
            }
          >
            {[...new Set([...types, ...(entry ? [entry.type] : [])])].map(
              (type) => (
                <option key={type}>{type}</option>
              ),
            )}
          </select>
          <label htmlFor="entry-aliases">
            Other names <span className="subtle">(comma separated)</span>
          </label>
          <Input
            id="entry-aliases"
            value={draft.aliases}
            onChange={(event) =>
              saveDraft({ ...draft, aliases: event.target.value })
            }
            placeholder="A nickname, alternate spelling"
          />
          <div className="editor-label">
            <label htmlFor="entry-body">Description and notes</label>
            <div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setPreview(false)}
              >
                Write
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setPreview(true)}
              >
                Preview
              </Button>
            </div>
          </div>
          {preview ? (
            <div className="markdown-preview edit-preview">
              {entry ? (
                <EntryMarkdown
                  sourceConcept={entry.concept}
                  workspace={workspace}
                  onNavigate={onNavigate}
                >
                  {draft.body || "*Nothing to preview yet.*"}
                </EntryMarkdown>
              ) : (
                <ReactMarkdown>
                  {draft.body || "*Nothing to preview yet.*"}
                </ReactMarkdown>
              )}
            </div>
          ) : (
            <>
              <div
                className="format-toolbar"
                role="group"
                aria-label="Text formatting"
              >
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label="Bold"
                  onClick={() => formatBody("bold")}
                >
                  <strong>B</strong>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label="Heading"
                  onClick={() => formatBody("heading")}
                >
                  H2
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label="List"
                  onClick={() => formatBody("list")}
                >
                  • List
                </Button>
              </div>
              <Textarea
                ref={bodyRef}
                id="entry-body"
                rows={12}
                value={draft.body}
                onChange={(event) =>
                  saveDraft({ ...draft, body: event.target.value })
                }
                placeholder="Write a description. Markdown formatting is supported."
              />
            </>
          )}
          <fieldset className="related-picker">
            <legend>Connect to other entries</legend>
            {workspace.entries
              .filter((row) => row.concept !== entry?.concept)
              .map((row) => (
                <label key={row.concept}>
                  <input
                    type="checkbox"
                    checked={draft.related.includes(row.concept)}
                    onChange={(event) =>
                      saveDraft({
                        ...draft,
                        related: event.target.checked
                          ? [...draft.related, row.concept]
                          : draft.related.filter((id) => id !== row.concept),
                      })
                    }
                  />
                  {row.title}
                  <span className="subtle"> · {row.type}</span>
                </label>
              ))}
          </fieldset>
          {outOfDate && (
            <div className="error-banner" role="alert">
              <p>
                This campaign changed while you were editing. Draft content is
                retained. Review the saved content below before confirming a
                replacement.
              </p>
              <strong>Latest saved content</strong>
              <div className="latest-body">
                {entry && (
                  <EntryMarkdown
                    sourceConcept={entry.concept}
                    workspace={workspace}
                    onNavigate={onNavigate}
                  >
                    {entry.body || "*No saved description*"}
                  </EntryMarkdown>
                )}
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  saveDraft({ ...draft, baseRevision: workspace.revision })
                }
              >
                Confirm replacement with my draft on latest version
              </Button>
            </div>
          )}
          {error && (
            <p className="error-banner" role="alert">
              {error} Your draft is still saved.
            </p>
          )}
          <div className="form-actions">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={saving || !draft.title.trim() || outOfDate}
            >
              Save entry
            </Button>
          </div>
        </form>
      </CardContent>
    </>
  );
}

function SourcesPanel({
  workspace,
  aiAvailable,
  model,
  maxChars,
  onAdd,
  onProcess,
  busy,
  error,
}: {
  workspace: Workspace;
  aiAvailable: boolean;
  model: string | null;
  maxChars: number;
  onAdd: (source: {
    title: string;
    date: string;
    text: string;
  }) => Promise<void>;
  onProcess: (id: string) => void;
  busy: boolean;
  error: string | null;
}) {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const emptyDraft: SourceDraft = {
    title: "",
    date: today,
    text: "",
    fileName: "",
  };
  const savedDraft = useSourceDrafts((state) => state.drafts[workspace.id]);
  const [draft, setDraft] = useState<SourceDraft>(
    () => savedDraft ?? emptyDraft,
  );
  const updateDraft = (next: SourceDraft) => {
    setDraft(next);
    useSourceDrafts.getState().put(workspace.id, next);
  };
  const clearDraft = () => {
    setDraft(emptyDraft);
    useSourceDrafts.getState().clear(workspace.id);
  };
  const { title, date, text, fileName } = draft;
  const setTitle = (title: string) => updateDraft({ ...draft, title });
  const setDate = (date: string) => updateDraft({ ...draft, date });
  const setText = (text: string) => updateDraft({ ...draft, text });
  const setFileName = (fileName: string) => updateDraft({ ...draft, fileName });
  const sourceJobs = (id: string) =>
    workspace.jobs.filter((job) => job.source_id === id);
  return (
    <section className="content-column">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Session notes and transcripts</p>
          <h2>Sources</h2>
          <p className="subtle">
            Save notes here, then choose when to ask AI to suggest campaign
            knowledge.
          </p>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Add a source</CardTitle>
          <CardDescription>
            Paste notes or choose a UTF-8 text or Markdown file.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="stack-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onAdd({ title: title.trim(), date, text })
                .then(clearDraft)
                .catch(() => undefined);
            }}
          >
            <label htmlFor="source-title">Source title</label>
            <Input
              id="source-title"
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Session 12: The Lantern Vault"
            />
            <label htmlFor="source-date">Session date</label>
            <Input
              id="source-date"
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
            <label htmlFor="source-file">
              Choose a .txt or .md file{" "}
              <span className="subtle">(optional)</span>
            </label>
            <Input
              id="source-file"
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              onChange={async (event) => {
                const input = event.currentTarget;
                input.setCustomValidity("");
                const file = input.files?.[0];
                if (!file) return;
                if (!/\.(txt|md)$/i.test(file.name)) {
                  input.setCustomValidity("Choose a .txt or .md file.");
                  input.reportValidity();
                  return;
                }
                const content = await file.text();
                setText(content);
                setFileName(file.name);
                if (!title) setTitle(file.name.replace(/\.(txt|md)$/i, ""));
              }}
            />
            <p className="hint">
              {fileName
                ? `Loaded ${fileName}. You can edit the text below.`
                : "Files are read as UTF-8 and stay in this campaign workspace."}
            </p>
            <label htmlFor="source-text">Source text</label>
            <Textarea
              id="source-text"
              required
              maxLength={maxChars}
              rows={10}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste session notes or a transcript here…"
            />
            <p className="hint">
              {text.length.toLocaleString()} / {maxChars.toLocaleString()}{" "}
              characters
            </p>
            {error && (
              <p role="alert" className="error-banner">
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={
                busy || !title.trim() || !text.trim() || text.length > maxChars
              }
            >
              <Plus /> Save source
            </Button>
          </form>
        </CardContent>
      </Card>
      <div className="source-list">
        <h3>Saved sources</h3>
        {workspace.sources.length ? (
          [...workspace.sources].reverse().map((source) => {
            const jobs = sourceJobs(source.id);
            const latest = jobs[jobs.length - 1];
            return (
              <Card key={source.id}>
                <CardHeader>
                  <div className="source-heading">
                    <div>
                      <CardTitle>{source.title}</CardTitle>
                      <CardDescription>
                        {source.date} · {source.text.length.toLocaleString()}{" "}
                        characters
                      </CardDescription>
                    </div>
                    <Badge
                      variant={
                        latest?.status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {latest?.status ?? "saved"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <details>
                    <summary>Read full source text</summary>
                    <pre className="source-text">{source.text}</pre>
                  </details>
                  {latest?.error && (
                    <p role="alert" className="error-banner">
                      {latest.error}
                    </p>
                  )}
                  {latest?.status === "ready" && (
                    <p role="status">Suggestions are ready in Review.</p>
                  )}
                  {latest?.status === "running" ? (
                    <p role="status">
                      Processing… this can take a few minutes.
                    </p>
                  ) : (
                    latest?.status !== "ready" && (
                      <div className="process-box">
                        <p>
                          AI may send this source to{" "}
                          {model ?? "the configured provider"} for extraction.
                          Provider charges may apply. Nothing is sent until you
                          select this button.
                        </p>
                        {!aiAvailable && (
                          <p className="hint">
                            AI is not configured on this computer. Manual
                            campaign editing still works.
                          </p>
                        )}
                        <Button
                          variant="outline"
                          disabled={!aiAvailable || busy}
                          onClick={() => onProcess(source.id)}
                        >
                          {latest?.status === "failed"
                            ? "Retry processing"
                            : "Review this source with AI"}
                        </Button>
                      </div>
                    )
                  )}
                </CardContent>
              </Card>
            );
          })
        ) : (
          <p className="empty-note">Sources you add will appear here.</p>
        )}
      </div>
    </section>
  );
}

function ReviewPanel({
  workspace,
  onNavigate,
  pending,
  safeBulk,
  onApply,
  busy,
  error,
}: {
  workspace: Workspace;
  onNavigate: (concept: string) => void;
  pending: Proposal[];
  safeBulk: Proposal[];
  onApply: (
    decisions: {
      id: string;
      action: "accept" | "reject";
      target?: string | null;
      body?: string;
    }[],
  ) => void;
  busy: boolean;
  error: string | null;
}) {
  const [choices, setChoices] = useState<Record<string, "accept" | "reject">>(
    {},
  );
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [bodies, setBodies] = useState<Record<string, string>>({});
  const eligible = pending.filter(
    (proposal) =>
      choices[proposal.id] === "reject" ||
      (choices[proposal.id] === "accept" &&
        (!proposal.needs_decision || targets[proposal.id])),
  );
  const sourceFor = (proposal: Proposal) =>
    workspace.sources.find((source) => source.id === proposal.source_id);
  const applySelection = () =>
    onApply(
      eligible.map((proposal) => ({
        id: proposal.id,
        action: choices[proposal.id] ?? "reject",
        ...(choices[proposal.id] === "accept"
          ? {
              target:
                targets[proposal.id] === "__new"
                  ? ""
                  : targets[proposal.id] || null,
              body: bodies[proposal.id] ?? proposal.body,
            }
          : {}),
      })),
    );
  const acceptClearSuggestions = () =>
    onApply(
      safeBulk
        .filter((proposal) => choices[proposal.id] !== "reject")
        .map((proposal) => ({
          id: proposal.id,
          action: "accept",
          body: bodies[proposal.id] ?? proposal.body,
        })),
    );
  return (
    <section className="content-column">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Suggestions from your sources</p>
          <h2>Review changes</h2>
          <p className="subtle">
            AI suggestions never change your campaign until you review and apply
            them.
          </p>
        </div>
        {safeBulk.length > 0 && (
          <Button
            variant="outline"
            disabled={
              busy ||
              !safeBulk.some((proposal) => choices[proposal.id] !== "reject")
            }
            onClick={acceptClearSuggestions}
          >
            Accept clear new entries
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error} Your suggestions are still available.
        </p>
      )}
      {pending.length ? (
        pending.map((proposal) => {
          const source = sourceFor(proposal);
          return (
            <Card key={proposal.id} className="proposal-card">
              <CardHeader>
                <div className="source-heading">
                  <div>
                    <Badge variant="outline">{proposal.type}</Badge>
                    <CardTitle>{proposal.title}</CardTitle>
                    <CardDescription>
                      {source?.title} · {source?.date}
                      {proposal.citation ? ` · ${proposal.citation}` : ""}
                    </CardDescription>
                  </div>
                  {proposal.needs_decision && (
                    <Badge variant="destructive">Choose identity</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="evidence-grid">
                  <div>
                    <h3>Suggested note</h3>
                    <Textarea
                      aria-label={`Suggested note for ${proposal.title}`}
                      rows={5}
                      value={bodies[proposal.id] ?? proposal.body}
                      onChange={(event) =>
                        setBodies({
                          ...bodies,
                          [proposal.id]: event.target.value,
                        })
                      }
                    />
                    <details className="evidence-box">
                      <summary>Read full source evidence</summary>
                      <p>{source?.text ?? "Source is unavailable."}</p>
                    </details>
                  </div>
                  <div>
                    <h3>Current campaign text</h3>
                    {proposal.target ? (
                      <div className="current-text">
                        <strong>
                          {workspace.entries.find(
                            (entry) => entry.concept === proposal.target,
                          )?.title ?? proposal.target}
                        </strong>
                        {(() => {
                          const target = workspace.entries.find(
                            (entry) => entry.concept === proposal.target,
                          );
                          return target ? (
                            <EntryMarkdown
                              sourceConcept={target.concept}
                              workspace={workspace}
                              onNavigate={onNavigate}
                            >
                              {target.body || "*No current notes*"}
                            </EntryMarkdown>
                          ) : (
                            <ReactMarkdown>*No current notes*</ReactMarkdown>
                          );
                        })()}
                      </div>
                    ) : (
                      <p className="subtle">
                        This is a new entry suggestion. Accepting adds it as a
                        source-attributed note.
                      </p>
                    )}
                    {(proposal.needs_decision ||
                      proposal.candidates.length > 0) && (
                      <div className="identity-choice">
                        <label htmlFor={`identity-${proposal.id}`}>
                          Apply this note to
                        </label>
                        <select
                          id={`identity-${proposal.id}`}
                          value={
                            targets[proposal.id] ??
                            (proposal.needs_decision
                              ? ""
                              : (proposal.target ?? ""))
                          }
                          onChange={(event) =>
                            setTargets({
                              ...targets,
                              [proposal.id]: event.target.value,
                            })
                          }
                        >
                          <option value="">Choose an entry…</option>
                          {proposal.candidates.map((id) => (
                            <option key={id} value={id}>
                              {workspace.entries.find(
                                (entry) => entry.concept === id,
                              )?.title ?? id}
                            </option>
                          ))}
                          <option value="__new">Create a separate entry</option>
                        </select>
                      </div>
                    )}
                  </div>
                </div>
                <div className="proposal-actions">
                  <Button
                    variant={
                      choices[proposal.id] === "accept" ? "default" : "outline"
                    }
                    onClick={() =>
                      setChoices({ ...choices, [proposal.id]: "accept" })
                    }
                  >
                    Accept suggestion
                  </Button>
                  <Button
                    variant={
                      choices[proposal.id] === "reject"
                        ? "destructive"
                        : "outline"
                    }
                    onClick={() =>
                      setChoices({ ...choices, [proposal.id]: "reject" })
                    }
                  >
                    Reject
                  </Button>
                  {choices[proposal.id] && (
                    <Badge variant="secondary">
                      {choices[proposal.id]} selected
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })
      ) : (
        <Card>
          <CardContent>
            <p className="empty-note">
              No suggestions are waiting. Add a source and choose “Review this
              source with AI” to get started.
            </p>
          </CardContent>
        </Card>
      )}
      {eligible.length > 0 && (
        <div className="sticky-review">
          <span>
            {eligible.length} decision{eligible.length === 1 ? "" : "s"} ready
            to apply
          </span>
          <Button disabled={busy} onClick={applySelection}>
            Apply selected decisions
          </Button>
        </div>
      )}
    </section>
  );
}

function HistoryPanel({
  workspace,
  onRestore,
  busy,
  error,
}: {
  workspace: Workspace;
  onRestore: (revision: string) => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <section className="content-column">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Saved campaign versions</p>
          <h2>History</h2>
          <p className="subtle">
            Restoring a version creates a new saved version, so you can always
            return here.
          </p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <ol className="history-list">
        {[...workspace.history].reverse().map((row) => (
          <li key={row.revision}>
            <Card>
              <CardContent>
                <div className="history-row">
                  <div>
                    <strong>{row.message}</strong>
                    <p>
                      {new Date(row.created_at).toLocaleString()} ·{" "}
                      <code>{row.revision.slice(0, 10)}</code>
                    </p>
                  </div>
                  {row.revision !== workspace.revision && (
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Restore “${row.message}”? The current campaign will remain in history.`,
                          )
                        )
                          onRestore(row.revision);
                      }}
                    >
                      Restore this version
                    </Button>
                  )}
                  {row.revision === workspace.revision && (
                    <Badge>Current version</Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}
