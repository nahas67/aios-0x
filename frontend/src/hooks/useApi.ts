/**
 * useApi — the single data-fetching hook. Handles loading, error, and
 * refresh. Components declare what they need; refresh() re-fetches on demand
 * (e.g. after a control action or an SSE tick that matters).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  status: number;
  refresh: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(0);
  const seq = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const result = await fetcherRef.current();
      if (seq.current !== my) return; // stale response, drop it
      setData(result);
      setError(null);
    } catch (err) {
      if (seq.current !== my) return;
      if (err instanceof ApiError) {
        setError(err.message);
        setStatus(err.status);
      } else {
        setError(String(err));
      }
    } finally {
      if (seq.current === my) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, status, refresh: load };
}
