export type Entry = {
  concept: string;
  title: string;
  type: string;
  body: string;
  aliases: string[];
  related: string[];
  editable: boolean;
};
export type Source = {
  id: string;
  title: string;
  date: string;
  text: string;
  created_at: string;
};
export type Proposal = {
  id: string;
  job_id: string;
  source_id: string;
  title: string;
  type: string;
  body: string;
  citation: string | null;
  target: string | null;
  candidates: string[];
  needs_decision: boolean;
  status: string;
};
export type Revision = {
  revision: string;
  message: string;
  created_at: string;
};
export type Campaign = {
  id: string;
  name: string;
  description: string;
  revision: string;
  entry_count: number;
};
export type Workspace = Campaign & {
  entries: Entry[];
  sources: Source[];
  jobs: {
    id: string;
    source_id: string;
    status: string;
    error?: string;
    recap?: string;
  }[];
  proposals: Proposal[];
  history: Revision[];
};
export type Config = {
  ai_available: boolean;
  model: string | null;
  max_source_chars: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/workspaces${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | { msg?: string; loc?: (string | number)[] }[];
    } | null;
    const detail = body?.detail;
    const explanation = Array.isArray(detail)
      ? detail
          .map(
            (item) =>
              `${item.loc?.slice(-1)[0] ?? "Field"}: ${item.msg ?? "check this value"}`,
          )
          .join(". ")
      : detail;
    throw new Error(
      explanation ||
        `Request failed (${response.status}). Please check the details and try again.`,
    );
  }
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("application/zip")) return (await response.blob()) as T;
  return (await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const api = {
  list: () => request<Campaign[]>(""),
  config: () => request<Config>("/config"),
  workspace: (id: string) => request<Workspace>(`/${id}`),
  create: (name: string, description: string) =>
    request<Workspace>("", json("POST", { name, description })),
  importBundle: async (name: string, file: File) =>
    request<Workspace>(`/import?name=${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: file,
    }),
  saveEntry: (
    id: string,
    entry: Omit<Entry, "concept" | "editable">,
    revision: string,
    concept?: string,
  ) =>
    request<Workspace>(
      concept
        ? `/${id}/entries/${encodeURIComponent(concept).replaceAll("%2F", "/")}`
        : `/${id}/entries`,
      json(concept ? "PUT" : "POST", { ...entry, base_revision: revision }),
    ),
  addSource: (
    id: string,
    source: { title: string; date: string; text: string },
  ) => request<Workspace>(`/${id}/sources`, json("POST", source)),
  processSource: (id: string, sourceId: string) =>
    request<Workspace>(
      `/${id}/sources/${sourceId}/process`,
      json("POST", { consent: true }),
    ),
  review: (
    id: string,
    revision: string,
    decisions: {
      id: string;
      action: "accept" | "reject";
      target?: string | null;
      body?: string;
    }[],
  ) =>
    request<Workspace>(
      `/${id}/review`,
      json("POST", { base_revision: revision, decisions }),
    ),
  restore: (id: string, revision: string, target: string) =>
    request<Workspace>(
      `/${id}/restore`,
      json("POST", { base_revision: revision, revision: target }),
    ),
  export: (id: string) => request<Blob>(`/${id}/export`),
};
