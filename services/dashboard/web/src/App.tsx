import { useState } from "react";
import { useStatus, useHistory } from "./useStatus";
import { ServiceHeader } from "./components/ServiceHeader";
import { Funnel } from "./components/Funnel";
import { Inbox } from "./components/Inbox";
import { KbPanel } from "./components/KbPanel";
import { WikiTable } from "./components/WikiTable";
import { Trend } from "./components/Trend";
import { Glossary } from "./components/Glossary";

type Tab = "status" | "glossar";

export default function App() {
  const { data, error } = useStatus();
  const { data: history } = useHistory();
  const [tab, setTab] = useState<Tab>("status");
  const [glossarMounted, setGlossarMounted] = useState(false);

  function selectTab(next: Tab) {
    setTab(next);
    if (next === "glossar") setGlossarMounted(true);
  }

  if (!data && !error) {
    return (
      <div className="app">
        <p className="muted">Lade Status…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="app">
        <p className="error">Dashboard-API nicht erreichbar: {error}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header>
        <h1>pnp-dashboard</h1>
        <nav className="tabs">
          <button className={tab === "status" ? "active" : ""} onClick={() => selectTab("status")}>
            Status
          </button>
          <button className={tab === "glossar" ? "active" : ""} onClick={() => selectTab("glossar")}>
            Glossar
          </button>
        </nav>
      </header>
      {tab === "status" && (
        <>
          <ServiceHeader crawl={data.crawl} kb={data.kb} exportStatus={data.export} />
          <Inbox actions={data.inbox} />
          <Funnel rows={data.funnel} />
          <KbPanel kb={data.kb} />
          <WikiTable exportStatus={data.export} />
          <Trend history={history} />
        </>
      )}
      {glossarMounted && (
        <div hidden={tab !== "glossar"}>
          <Glossary />
        </div>
      )}
    </div>
  );
}
