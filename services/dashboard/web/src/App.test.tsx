import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

const campaign = {
  id: "a".repeat(32),
  name: "Moonfall",
  description: "",
  revision: "r1",
  entry_count: 0,
};
const renderApp = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <App />
    </QueryClientProvider>,
  );
const reviewWorkspace = {
  ...campaign,
  entries: [
    {
      concept: "locations/willow",
      title: "Willow Quay",
      type: "Location",
      body: "A riverside market.",
      aliases: [],
      related: [],
      editable: true,
    },
  ],
  sources: [
    {
      id: "b".repeat(32),
      title: "Session 9",
      date: "2026-10-28",
      text: "Mira found a brass key near Willow Quay.",
      created_at: "2026-10-28T12:00:00Z",
    },
  ],
  jobs: [],
  history: [
    { revision: "r1", message: "Created", created_at: "2026-10-28T12:00:00Z" },
  ],
  proposals: [
    {
      id: "clear",
      job_id: "job",
      source_id: "b".repeat(32),
      title: "The Glass Bell",
      type: "Item",
      body: "It rings at dawn.",
      citation: null,
      target: null,
      candidates: [],
      needs_decision: false,
      status: "pending",
    },
    {
      id: "reject",
      job_id: "job",
      source_id: "b".repeat(32),
      title: "The Muddy Coin",
      type: "Item",
      body: "A copper token.",
      citation: null,
      target: null,
      candidates: [],
      needs_decision: false,
      status: "pending",
    },
    {
      id: "ambiguous",
      job_id: "job",
      source_id: "b".repeat(32),
      title: "Willow Quay",
      type: "Location",
      body: "A hidden cellar sits under the quay.",
      citation: null,
      target: null,
      candidates: ["locations/willow"],
      needs_decision: true,
      status: "pending",
    },
  ],
};
const importedWorkspace = {
  ...campaign,
  entries: [
    {
      concept: "npcs/runa",
      title: "Runa",
      type: "NPC",
      body: "See [root link](/locations/moonfall-pier.md), [relative link](../locations/moonfall-pier.md), [outside](https://example.com), [protocol relative](//locations/moonfall-pier.md), and [wrong prefix](/archive/locations/moonfall-pier.md).",
      aliases: [],
      related: [],
      editable: true,
    },
    {
      concept: "locations/moonfall-pier",
      title: "Moonfall Pier",
      type: "Location",
      body: "A quiet landing by the lighthouse.",
      aliases: [],
      related: [],
      editable: true,
    },
    {
      concept: "sessions/session-one",
      title: "Session One",
      type: "Session",
      body: "Imported material retained as read-only content.",
      aliases: [],
      related: [],
      editable: false,
    },
  ],
  sources: [],
  jobs: [],
  proposals: [],
  history: [{ revision: "r1", message: "Imported", created_at: "2026-10-28T12:00:00Z" }],
};
function serveImportedWorkspace() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/config"))
        return Response.json({ ai_available: false, model: null, max_source_chars: 120000 });
      if (url === "/api/workspaces") return Response.json([campaign]);
      if (url === `/api/workspaces/${campaign.id}`) return Response.json(importedWorkspace);
      return new Response("", { status: 404 });
    }),
  );
}
function serveReviewWorkspace() {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/config"))
        return Response.json({
          ai_available: false,
          model: null,
          max_source_chars: 120000,
        });
      if (url === "/api/workspaces") return Response.json([campaign]);
      if (url.endsWith("/api/workspaces"))
        return Response.json(reviewWorkspace);
      if (url.endsWith(`/${campaign.id}`))
        return Response.json(reviewWorkspace);
      if (url.endsWith("/review")) return Response.json(reviewWorkspace);
      return new Response("", { status: 404 });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
async function openReviewCampaign() {
  fireEvent.click(await screen.findByRole("button", { name: /moonfall/i }));
  const navigation = await screen.findByRole("navigation", {
    name: /campaign sections/i,
  });
  fireEvent.click(within(navigation).getAllByRole("button")[2]);
  await screen.findByText("The Glass Bell");
}
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/config"))
        return Response.json({
          ai_available: false,
          model: null,
          max_source_chars: 120000,
        });
      if (init?.method === "POST" && url.endsWith("/api/workspaces"))
        return Response.json({
          ...campaign,
          entries: [],
          sources: [],
          jobs: [],
          proposals: [],
          history: [],
        });
      if (url.endsWith("/api/workspaces")) return Response.json([]);
      if (url.endsWith(`/${campaign.id}`))
        return Response.json({
          ...campaign,
          entries: [],
          sources: [],
          jobs: [],
          proposals: [],
          history: [],
        });
      return new Response("", { status: 404 });
    }),
  );
});

describe("campaign workbench startup", () => {
  it("offers campaign creation and bundle import without requiring the technical dashboard", () => {
    renderApp();

    expect(
      screen.getByRole("heading", { name: /campaign workbench/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create campaign/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/choose a campaign bundle zip/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /technical dashboard/i }),
    ).toBeInTheDocument();
  });

  it("opens a root-relative concept link in the workbench", async () => {
    serveImportedWorkspace();
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: /moonfall/i }));
    fireEvent.click(await screen.findByRole("button", { name: /runa/i }));
    expect(screen.getByRole("link", { name: "outside" })).toHaveAttribute("href", "https://example.com");
    expect(screen.getByRole("link", { name: "protocol relative" })).toHaveAttribute("href", "//locations/moonfall-pier.md");
    expect(screen.getByRole("link", { name: "wrong prefix" })).toHaveAttribute("href", "/archive/locations/moonfall-pier.md");

    fireEvent.click(screen.getByRole("link", { name: "root link" }));

    expect(
      await screen.findByText("A quiet landing by the lighthouse.", {
        exact: true,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Campaign sections" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /runa/i }));
    fireEvent.click(screen.getByRole("link", { name: "relative link" }));
    expect(
      await screen.findByText("A quiet landing by the lighthouse.", {
        exact: true,
      }),
    ).toBeInTheDocument();
  });

  it("explains imported read-only content and does not offer Edit", async () => {
    serveImportedWorkspace();
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: /moonfall/i }));
    fireEvent.click(await screen.findByRole("button", { name: /session one/i }));

    expect(
      screen.getByText("Imported material retained as read-only content."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Imported Session content is read-only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit entry" })).not.toBeInTheDocument();
  });

  it("creates and opens a campaign from the start screen", async () => {
    renderApp();

    fireEvent.change(
      await screen.findByLabelText("Campaign name", {
        selector: "#campaign-name",
      }),
      { target: { value: "Moonfall" } },
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: /create campaign/i })[0],
    );

    expect(
      await screen.findByRole("heading", { name: "Moonfall" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/workspaces",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("formats an entry description with the bold control and previews the formatted text", async () => {
    renderApp();
    fireEvent.change(
      await screen.findByLabelText("Campaign name", {
        selector: "#campaign-name",
      }),
      { target: { value: "Moonfall" } },
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: /create campaign/i })[0],
    );
    await screen.findByRole("heading", { name: "Moonfall" });
    fireEvent.click(
      screen.getAllByRole("button", { name: /add an entry/i })[0],
    );
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Runa" },
    });
    fireEvent.change(screen.getByLabelText("Description and notes"), {
      target: { value: "A fearless guide." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Bold" }));
    expect(screen.getByLabelText("Description and notes")).toHaveValue(
      "**A fearless guide.**",
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(
      screen.getByText("A fearless guide.", { selector: "strong" }),
    ).toBeInTheDocument();
  });

  it("keeps an unsaved source draft when switching campaign sections", async () => {
    renderApp();
    fireEvent.change(
      await screen.findByLabelText("Campaign name", {
        selector: "#campaign-name",
      }),
      { target: { value: "Moonfall" } },
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: /create campaign/i })[0],
    );
    const navigation = await screen.findByRole("navigation", {
      name: /campaign sections/i,
    });
    fireEvent.click(within(navigation).getAllByRole("button")[1]);
    fireEvent.change(screen.getByLabelText("Source title"), {
      target: { value: "Session notes" },
    });
    fireEvent.change(screen.getByLabelText("Source text"), {
      target: { value: "The group found a silver bell." },
    });
    fireEvent.click(within(navigation).getAllByRole("button")[0]);
    fireEvent.click(within(navigation).getAllByRole("button")[1]);

    expect(screen.getByLabelText("Source title")).toHaveValue("Session notes");
    expect(screen.getByLabelText("Source text")).toHaveValue(
      "The group found a silver bell.",
    );
  });

  it("bulk accepts edited clear additions but skips a suggestion marked for rejection", async () => {
    const fetchMock = serveReviewWorkspace();
    renderApp();
    await openReviewCampaign();

    const clearCard = screen
      .getByText("The Glass Bell")
      .closest<HTMLElement>('[data-slot="card"]')!;
    fireEvent.change(within(clearCard).getByLabelText(/suggested note/i), {
      target: { value: "Edited: it rings only at dawn." },
    });
    const rejectedCard = screen
      .getByText("The Muddy Coin")
      .closest<HTMLElement>('[data-slot="card"]')!;
    fireEvent.click(
      within(rejectedCard).getByRole("button", { name: "Reject" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /accept clear new entries/i }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workspaces/" + campaign.id + "/review",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/review"),
    )!;
    const payload = JSON.parse(String(call[1]?.body));
    expect(payload.decisions).toEqual([
      { id: "clear", action: "accept", body: "Edited: it rings only at dawn." },
    ]);
  });

  it("requires an explicit identity choice and sends an empty target to create a separate entry", async () => {
    const fetchMock = serveReviewWorkspace();
    renderApp();
    await openReviewCampaign();
    const proposalCard = screen
      .getByText("A hidden cellar sits under the quay.")
      .closest<HTMLElement>('[data-slot="card"]')!;
    const apply = within(proposalCard).getByRole("button", {
      name: /accept suggestion/i,
    });
    fireEvent.click(apply);
    expect(
      screen.queryByRole("button", { name: /apply selected decisions/i }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/apply this note to/i), {
      target: { value: "__new" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /apply selected decisions/i }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workspaces/" + campaign.id + "/review",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/review"),
    )!;
    const payload = JSON.parse(String(call[1]?.body));
    expect(payload.decisions).toEqual([
      {
        id: "ambiguous",
        action: "accept",
        target: "",
        body: "A hidden cellar sits under the quay.",
      },
    ]);
  });
});
