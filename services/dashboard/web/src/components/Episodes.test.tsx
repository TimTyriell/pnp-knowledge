import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { Episodes } from "./Episodes";

const response = {
  current: { extract: "7", synth: "6", state: "6" },
  seasons: [
    { key: "P", label: "Prolog", episodes: 1, transcripts: 1, frozen: { frozen_at: "2026-11-11T10:00:00Z", prompt_versions: { extract: "6", synth: "6", state: null }, models: {}, counts: { sessions: 1, bodies: 0, bodies_missing: 0, state_sessions: 0 } } },
    { key: "S1", label: "Staffel 1", episodes: 1, transcripts: 1, frozen: null },
  ],
  unlisted_transcripts: ["loose-session"],
};
const episodes = { seasons: { P: { label: "Prolog" }, S1: { label: "Staffel 1" } }, episodes: [{ video_id: "p1", date: "2025-01-01", season: "P", team: "A" }, { video_id: "s1", date: "2026-01-01", season: "S1", team: "A" }] };

beforeEach(() => {
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url) === "/api/seasons") return Response.json(response);
    if (String(url) === "/api/episodes") return Response.json(episodes);
    if (String(url) === "/api/seasons/S1/freeze" && init?.method === "POST") return Response.json({ ok: true, output: "Staffel S1 eingefroren" });
    return new Response("", { status: 404 });
  }));
});

it("marks a frozen season and offers freezing for an active one", async () => {
  render(<Episodes funnel={[]} />);
  expect(await screen.findByText(/eingefroren seit/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Einfrieren" })).toBeInTheDocument();
});

it("warns about transcripts without an episode", async () => {
  render(<Episodes funnel={[]} />);
  expect(await screen.findByText(/ohne Eintrag in episodes.yaml/)).toBeInTheDocument();
});

it("freezes an active season, shows the result, and reloads status", async () => {
  render(<Episodes funnel={[]} />);
  fireEvent.click(await screen.findByRole("button", { name: "Einfrieren" }));
  expect(await screen.findByText("Staffel S1 eingefroren")).toBeInTheDocument();
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/seasons/S1/freeze", expect.objectContaining({ method: "POST" })));
});
