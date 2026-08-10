import { useCallback, useEffect, useRef, useState } from "react";
import type { DashboardStatus, Episodes, Glossary, HistoryResponse } from "./types";

const POLL_MS = 10_000;

function usePolled<T>(url: string): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const json = (await res.json()) as T;
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    function schedule() {
      if (document.hidden) return;
      tick();
    }

    schedule();
    timer.current = window.setInterval(schedule, POLL_MS);
    document.addEventListener("visibilitychange", schedule);

    return () => {
      cancelled = true;
      window.clearInterval(timer.current);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, [url]);

  return { data, error };
}

export function useStatus() {
  return usePolled<DashboardStatus>("/api/status");
}

export function useHistory(days = 90) {
  return usePolled<HistoryResponse>(`/api/history?days=${days}`);
}

function useOnce<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json() as Promise<T>;
      })
      .then((json) => {
        setData(json);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [url]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}

export function useGlossary() {
  return useOnce<Glossary>("/api/glossary");
}

// Changes once per session, not every 10s — one fetch, with reload for when a
// title was just filled in.
export function useEpisodes() {
  return useOnce<Episodes>("/api/episodes");
}
