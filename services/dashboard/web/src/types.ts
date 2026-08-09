export type ServiceState = "ok" | "stale" | "missing" | "offline";

export interface Action {
  service: string;
  kind: string;
  label: string;
  ref: string;
}

export interface LastRun {
  run_id: string;
  started_at: string | null;
  ended_at: string | null;
  ok: boolean;
  error: string | null;
  counts: Record<string, unknown>;
}

export interface ServiceStatus {
  state?: ServiceState;
  error?: string;
  schema?: number;
  service?: string;
  generated_at?: string;
  last_run?: LastRun | null;
  items?: Record<string, unknown>[];
  actions?: Action[];
  // pnp-kb extras
  head?: string;
  session_tags?: string[];
  counts_by_type?: Record<string, number>;
  conflicts?: Record<string, unknown>[];
}

export interface FunnelRow {
  video_id: string | null;
  video_date: string | null;
  stem: string | null;
  downloaded: boolean | null;
  transcribed: boolean | null;
  mapped: boolean | null;
  exported: boolean | null;
  in_bundle: boolean;
  committed_at: string | null;
  lead_time_days: number | null;
}

export interface DashboardStatus {
  crawl: ServiceStatus;
  kb: ServiceStatus;
  export: ServiceStatus;
  funnel: FunnelRow[];
  inbox: Action[];
}

export interface HistoryPoint {
  ts: string;
  [key: string]: unknown;
}

export interface HistoryResponse {
  crawl: HistoryPoint[];
  export: HistoryPoint[];
}

export type AliasSource = "canonical" | "merge" | "registry";

export interface GlossaryAlias {
  name: string;
  count: number;
  source: AliasSource;
}

export interface GlossaryEntity {
  concept_id: string;
  type: string;
  canonical_name: string;
  pinned: boolean;
  important: boolean;
  mention_count: number;
  total_count: number;
  aliases: GlossaryAlias[];
}

export interface Glossary {
  stale: boolean;
  rules_mtime: string | null;
  registry_mtime: string | null;
  types: string[];
  entities: GlossaryEntity[];
}

export type Edit =
  | { op: "rename"; concept_id: string; name: string }
  | { op: "add_alias"; concept_id: string; alias: string }
  | { op: "delete_alias"; concept_id: string; alias: string; source: AliasSource; unfold_ack?: boolean };

export interface SyncPreview {
  ok: boolean;
  diff: string;
  warnings: string[];
  written: boolean;
}
