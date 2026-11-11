import { expect, test } from "./fixtures.ts";

test("estimates and starts a fictional season run from Folgen", async ({ page }) => {
  const frozen = {
    frozen_at: "2026-11-04T10:00:00Z",
    prompt_versions: { extract: "6", synth: "6", state: null },
    models: {},
    counts: { sessions: 1, bodies: 1, bodies_missing: 0, state_sessions: 0 },
  };
  const seasons = {
    current: { extract: "7", synth: "6", state: "6" },
    seasons: [
      { key: "P", label: "Prolog", episodes: 1, transcripts: 1, frozen },
      { key: "S1", label: "Staffel 1", episodes: 1, transcripts: 1, frozen: null },
    ],
    unlisted_transcripts: ["fictional-unlisted-session"],
  };
  let running = false;
  const status = { crawl: {}, kb: {}, export: {}, funnel: [], inbox: [] };
  await page.route("**/api/seasons", (route) => route.fulfill({ json: seasons }));
  await page.route("**/api/seasons/*/freeze", (route) => route.fulfill({ json: { ok: true, output: "frozen" } }));
  await page.route("**/api/runs/estimate", (route) => route.fulfill({ json: { ok: true, output: "fictional estimate" } }));
  await page.route("**/api/runs", async (route) => {
    if (route.request().method() === "POST") {
      running = true;
      await route.fulfill({ status: 202, json: { ok: true, output: "started" } });
    } else await route.fallback();
  });
  await page.route("**/api/runs/current", (route) => route.fulfill({ json: running
    ? { running: true, kind: "run", thaw: [], started_at: "2026-11-04T12:00:00Z", exit_code: null, log_tail: "fictional run started", last_run: null }
    : { running: false, kind: null, thaw: [], started_at: null, exit_code: null, log_tail: "", last_run: null } }));
  await page.route("**/api/status", (route) => route.fulfill({ json: status }));
  await page.route("**/api/episodes", (route) => route.fulfill({ json: { seasons: { P: { label: "Prolog" }, S1: { label: "Staffel 1" } }, episodes: [
    { video_id: "fictional-p", date: "2025-01-01", season: "P", team: "A", title: "Fictional Prolog" },
    { video_id: "fictional-s1", date: "2026-01-01", season: "S1", team: "A", title: "Fictional Staffel 1" },
  ] } }));
  await page.route("**/api/history*", (route) => route.fulfill({ json: { crawl: [], export: [] } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Technical dashboard" }).click();
  await page.getByRole("button", { name: "Folgen" }).click();
  await page.getByRole("button", { name: "Kosten schätzen" }).click();
  await expect(page.getByText("fictional estimate")).toBeVisible();
  await page.getByLabel("Kosten gesehen").check();
  await page.getByRole("button", { name: "Lauf starten" }).click();
  await expect(page.getByText("fictional run started")).toBeVisible();
});
