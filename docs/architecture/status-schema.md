# Status schema (v1)

Contract between the three toolchain repos and `services/dashboard`. Each
producer writes/serves a JSON object matching this envelope; the dashboard
only reads and merges — it never re-derives service-internal state.

## Envelope

```jsonc
{
  "schema": 1,
  "service": "pnp-crawl",              // "pnp-crawl" | "pnp-kb" | "pnp-export-data"
  "generated_at": "2026-08-09T12:00:00Z",  // UTC ISO 8601, when this snapshot was built
  "last_run": {
    "run_id": "20260805T212123Z-25696",
    "started_at": "2026-08-05T21:21:23Z",
    "ended_at": "2026-08-05T21:45:01Z",
    "duration_s": 1418.0,              // optional; null if timestamps unparseable
    "ok": true,
    "error": null,                     // set when ok=false
    "counts": { },                     // service-specific, see below
    "usage": { }                       // optional; LLM token accounting, see below
  },
  "items": [ ],                        // service-specific rows, see below
  "actions": [                         // things waiting on a human
    { "kind": "unresolved_speaker", "label": "…", "ref": "…" }
  ]
}
```

`last_run` is `null` if no run has ever recorded metadata (fresh checkout).

## Source of truth per field

- `generated_at`: wall-clock time the status file/response was built, not the
  last run time. Consumers use this for staleness detection.
- `actions[]`: only the producing service decides what belongs here. The
  dashboard concatenates and groups by `kind`, it does not interpret `kind`
  values itself.

## service: pnp-crawl

File: `pnp-crawl/status/status.json`, written by
`pipeline_status.py --json`. History: `pnp-crawl/status/history.jsonl`
(one line per write, schema below).

`last_run.counts`: `{"records": N, "errors": N, "audio_seconds": F}` folded
from the newest `logs/pipeline_*.jsonl`.

`items[]`: one row per known video —
`{stem, video_id, video_date, url, downloaded, transcribed, mapped,
exported, speakers_unresolved: [label, ...]}`.

`actions[]` kinds: `unresolved_speaker` (`ref` = stem), `pending_stage`
(`ref` = stem, `label` = next stage name).

`history.jsonl` line: `{ts, downloaded, transcribed, mapped, exported, unresolved}`
(counts across all `items`).

## service: pnp-kb

Served live: `GET http://127.0.0.1:8070/status` (no local file needed by
consumers; the KB also persists `services/kb/state/last_run.json` +
`state/history.jsonl` for its own history endpoint).

`last_run.counts`: `{"entities_by_type": {...}, "conflicts_open": N,
"sessions_ingested": N}`.

`last_run.usage` (pnp-kb only, added 2026-09-05): LLM token accounting for the
run, from the `usage` block the API returns on every completion.

```jsonc
"usage": {
  "llm_calls": 412,
  "tokens": { "prompt": 1840233, "completion": 233911 },
  "by_model": {
    "deepseek-v4-pro":   { "calls": 96,  "prompt_tokens": 812004, "completion_tokens": 150221 },
    "deepseek-v4-flash": { "calls": 316, "prompt_tokens": 1028229, "completion_tokens": 83690 }
  }
  // "cost" and "cost_currency" appear ONLY when prices are configured
}
```

Token counts are facts reported by the API and are always present. **Cost is
opt-in and never estimated**: a `cost` key appears for a model only when both
`PNP_PRICE_IN_<MODEL>` and `PNP_PRICE_OUT_<MODEL>` are set (price per 1M
tokens; `<MODEL>` uppercased with non-alphanumerics as underscores). Absent
cost therefore means "not priced", never "free" — consumers must not default it
to zero.

Both `duration_s` and `usage` are additive; every pre-existing key keeps its
meaning, so an older consumer is unaffected.

`items[]`: one row per session concept —
`{concept, id, video_id, date, title, quality, unsicher_ratio, committed_at}`.
`video_id` is extracted from the session frontmatter's `resource` URL;
`null` if not parseable.

Additional top-level fields (KB-specific, additive — not part of the shared
envelope but present in the live response): `head`, `session_tags`,
`conflicts: [{file, id, concept, title, timestamp}]`.

`actions[]` kinds: `conflict` (`ref` = conflict file name).

## service: pnp-export-data

File: `pnp-export-data/status/status.json`, written by `05_report.py`.
History: `pnp-export-data/status/history.jsonl`.

`last_run.counts`: `{"uploaded": N, "skipped_new": N, "failed": N,
"dry_run": bool}` folded from the newest `logs/*.jsonl`.

`items[]`: the `ki_pages` rows —
`{title, url, type, ki_last_edit, last_edit, last_editor, ki_state, bytes,
ki_bytes, anomalies: [...]}`.

`actions[]` kinds: `harvest` (human edit pending re-ingest into the KB,
`ref` = harvest file), `stub` (planned page not yet created, `ref` = wiki
title, `url` = direct link to the wiki's create-page editor for that title
— clicking it opens `?action=edit` on the non-existing page), `edited` (KI
region hand-edited, blocks re-merge, `ref` = page title), `anomaly`
(`ref` = page title, `label` = anomaly type).

`url` is optional on any action — only `stub` sets it today. The dashboard
renders `label`/`ref` as a link when present, plain text otherwise.

`history.jsonl` line: `{ts, pages_ki, pages_clean, pages_edited, uploaded,
failed}`.

## Join key across repos

The YouTube **video_id** is the only reliable anchor across pnp-crawl and
pnp-kb (crawl stems were renamed 2026-08; date alone collides on multi-session
days). Fall back to `video_date` / session `date` when `video_id` is missing
on either side. Wiki items are per-entity, not per-session — they don't join
into the funnel; they stay in their own dashboard panel.

## Staleness

A snapshot older than `generated_at + 48h` should be flagged stale by
consumers. This is a dashboard-side judgement call, not encoded in the
schema itself.
