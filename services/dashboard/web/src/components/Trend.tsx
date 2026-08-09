import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import type { HistoryResponse } from "../types";

export function Trend({ history }: { history: HistoryResponse | null }) {
  if (!history) return null;

  const crawlData = history.crawl.map((p) => ({
    ts: String(p.ts).slice(0, 10),
    exported: Number(p.exported ?? 0),
    unresolved: Number(p.unresolved ?? 0),
  }));

  const exportData = history.export.map((p) => ({
    ts: String(p.ts).slice(0, 10),
    pages_clean: Number(p.pages_clean ?? 0),
    pages_edited: Number(p.pages_edited ?? 0),
  }));

  return (
    <section className="panel">
      <h2>Trend</h2>
      <div className="trend-grid">
        <div>
          <h3>Crawl: exportierte Sessions</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={crawlData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="exported" stroke="var(--accent)" dot={false} />
              <Line type="monotone" dataKey="unresolved" stroke="var(--warn)" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3>Wiki: Seiten nach Zustand</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={exportData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="pages_clean" stroke="var(--ok)" dot={false} />
              <Line type="monotone" dataKey="pages_edited" stroke="var(--warn)" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
