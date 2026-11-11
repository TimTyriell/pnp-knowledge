import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RunPanel, isPeak } from "./RunPanel";

const status = { running: false, kind: null, thaw: [], started_at: null, exit_code: null, log_tail: "", last_run: null };
const seasons = { current: { extract: "7", synth: "6", state: "6" }, seasons: [{ key: "P", label: "Prolog", episodes: 1, transcripts: 1, frozen: { frozen_at: "2026-11-11T10:00:00Z", prompt_versions: { extract: "6", synth: "6", state: null }, models: {}, counts: { sessions: 1, bodies: 0, bodies_missing: 0, state_sessions: 0 } } }], unlisted_transcripts: [] };
let calls: Array<[RequestInfo | URL, RequestInit | undefined]>;
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push([url, init]);
    if (String(url) === "/api/seasons") return Response.json(seasons);
    if (String(url) === "/api/runs/current") return Response.json(status);
    if (String(url) === "/api/runs/estimate") return Response.json({ ok: true, output: "estimate output" });
    if (String(url) === "/api/runs") return Response.json({ ok: true, output: "started" });
    return new Response("", { status: 404 });
  }));
});

it("start stays disabled until an estimate is shown and confirmed", async () => {
  render(<RunPanel />);
  const start = await screen.findByRole("button", { name: "Lauf starten" });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Kosten schätzen" }));
  await screen.findByText("estimate output");
  fireEvent.click(screen.getByLabelText("Kosten gesehen"));
  expect(start).toBeEnabled();
});

it("keeps start disabled after an unsuccessful frozen-state estimate", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push([url, init]);
    if (String(url) === "/api/seasons") return Response.json(seasons);
    if (String(url) === "/api/runs/current") return Response.json(status);
    if (String(url) === "/api/runs/estimate") return Response.json({ ok: false, output: "Estimate blocked: frozen state is incomplete." });
    if (String(url) === "/api/runs") return Response.json({ ok: true, output: "started" });
    return new Response("", { status: 404 });
  }));
  render(<RunPanel />);
  fireEvent.click(screen.getByRole("button", { name: "Kosten schätzen" }));
  await screen.findByText("Estimate blocked: frozen state is incomplete.");
  fireEvent.click(screen.getByLabelText("Kosten gesehen"));
  expect(screen.getByRole("button", { name: "Lauf starten" })).toBeDisabled();
});

it("sends the thawed seasons with the start request", async () => {
  render(<RunPanel />);
  fireEvent.click(await screen.findByLabelText("Prolog einmalig neu lesen"));
  fireEvent.click(screen.getByRole("button", { name: "Kosten schätzen" }));
  await screen.findByText("estimate output");
  fireEvent.click(screen.getByLabelText("Kosten gesehen"));
  fireEvent.click(screen.getByRole("button", { name: "Lauf starten" }));
  await waitFor(() => expect(calls.some(([url, init]) => String(url) === "/api/runs" && !!init?.body)).toBe(true));
  expect(JSON.parse(String(calls.find(([url]) => String(url) === "/api/runs")?.[1]?.body))).toEqual({ kind: "run", thaw: ["P"], confirm: true });
});

it("changing the selection clears the estimate", async () => {
  render(<RunPanel />);
  fireEvent.click(screen.getByRole("button", { name: "Kosten schätzen" }));
  await screen.findByText("estimate output");
  fireEvent.click(screen.getByLabelText("Prolog einmalig neu lesen"));
  expect(screen.queryByText("estimate output")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Lauf starten" })).toBeDisabled();
});

it("discards an estimate that finishes after the run kind changes", async () => {
  let finishEstimate!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    if (String(url) === "/api/seasons") return Response.json(seasons);
    if (String(url) === "/api/runs/current") return Response.json(status);
    if (String(url) === "/api/runs/estimate") return await new Promise<Response>((resolve) => { finishEstimate = resolve; });
    return new Response("", { status: 404 });
  }));
  render(<RunPanel />);
  fireEvent.click(screen.getByRole("button", { name: "Kosten schätzen" }));
  fireEvent.click(screen.getByLabelText("Status-Pass (pnp state)"));
  fireEvent.click(screen.getByLabelText("Kosten gesehen"));
  await act(async () => {
    finishEstimate(Response.json({ ok: true, output: "stale estimate" }));
  });
  expect(screen.queryByText("stale estimate")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Lauf starten" })).toBeDisabled();
});

it("detects UTC peak windows", () => {
  expect(isPeak(new Date("2026-11-11T07:00:00Z"))).toBe(true);
  expect(isPeak(new Date("2026-11-11T12:00:00Z"))).toBe(false);
  expect(isPeak(new Date("2026-11-14T07:00:00Z"))).toBe(false);
});
