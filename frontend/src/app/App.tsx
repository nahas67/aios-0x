/**
 * Main application shell. Wires the navigation registry to the Shell component
 * with hash-based routing, SSE stream, periodic executive/gates refresh,
 * identity-aware auth token, and system banner.
 *
 * SECURITY: Shows LoginGate when not authenticated. Protected workspaces
 * only load after server-side identity is confirmed via /api/v1/session/me.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { executiveApi } from "../api/endpoints";
import { onStream, startStream, stopStream } from "../api/stream";
import { LoginGate } from "../components/LoginGate";
import { useApi } from "../hooks/useApi";
import { useIdentity } from "../stores/identity";
import { Shell } from "./Shell";
import { NAV_ITEMS } from "./registry";

function useHashRoute(): [string, (id: string) => void] {
  const parse = useCallback(() => {
    const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0] || "deck";
    return NAV_ITEMS.some((n) => n.id === raw) ? raw : "deck";
  }, []);

  const [route, setRoute] = useState(parse);

  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, [parse]);

  const navigate = useCallback(
    (id: string) => {
      window.location.hash = `/${id}`;
    },
    [],
  );

  return [route, navigate];
}

/** Protected application — only rendered after authentication. */
function ProtectedApp() {
  const [route, navigate] = useHashRoute();

  // Refresh executive + gates on SSE tick (throttled to 5s)
  const execApi = useApi(() => executiveApi.get());
  const gatesApi = useApi(() => executiveApi.gates());
  const lastRefresh = useRef(0);

  useEffect(() => {
    const off = onStream((s) => {
      if (s.status !== "live" || !s.frame) return;
      const now = Date.now();
      if (now - lastRefresh.current < 5_000) return;
      lastRefresh.current = now;
      execApi.refresh();
      gatesApi.refresh();
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Periodic full refresh every 30s
  useEffect(() => {
    const t = window.setInterval(() => {
      execApi.refresh();
      gatesApi.refresh();
    }, 30_000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Start SSE after authentication
  useEffect(() => {
    startStream();
    return () => stopStream();
  }, []);

  const item = NAV_ITEMS.find((n) => n.id === route) ?? NAV_ITEMS[0];
  const Page = item.component;

  return (
    <Shell
      nav={NAV_ITEMS}
      current={route}
      onNavigate={navigate}
      executive={execApi.data}
      gates={gatesApi.data}
    >
      <Page executive={execApi.data} gates={gatesApi.data} onNavigate={navigate} />
    </Shell>
  );
}

export function App() {
  const identity = useIdentity();

  if (!identity.authenticated) {
    return <LoginGate />;
  }

  return <ProtectedApp />;
}
