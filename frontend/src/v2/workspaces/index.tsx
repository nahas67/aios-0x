/**
 * V2 app root. Wires identity (server-resolved), the terminal shell, and the
 * 11 workspaces in 5 groups. When the server requires no token (dev mode),
 * session/me answers anonymously and the UI enters directly — no fake login.
 */
import { useCallback, useEffect, useState } from "react";
import { Shell, useHashRoute, type NavDef } from "../shell";
import { authenticateWithToken, setIdentity, useIdentity, type Role } from "../../stores/identity";
import { Deck, OrdersPage, OpportunitiesPage, PortfolioPage } from "./trade";
import { RiskCenter, ApprovalsPage } from "./safety";
import { AgentsPage, WorldPage } from "./intel";
import { KnowledgePage, CalibrationPage, TracePage } from "./research";
import { KernelPage, AuditPage, ConsolePage, SettingsPage } from "./system";


export const NAV: NavDef[] = [
  { id: "deck", label: "Command Deck", icon: "gauge", group: "trade" },
  { id: "portfolio", label: "Portfolio", icon: "wallet", group: "trade" },
  { id: "orders", label: "Orders & Tape", icon: "swap", group: "trade" },
  { id: "opportunities", label: "Opportunities", icon: "target", group: "trade" },

  { id: "risk", label: "Risk Center", icon: "shield", group: "safety" },
  { id: "approvals", label: "Approvals", icon: "scale", group: "safety" },

  { id: "agents", label: "Agents", icon: "agents", group: "intel" },
  { id: "world", label: "World", icon: "globe", group: "intel" },

  { id: "knowledge", label: "Knowledge", icon: "book", group: "research" },
  { id: "calibration", label: "Calibration", icon: "pulse", group: "research" },
  { id: "trace", label: "Decision Trace", icon: "flask", group: "research" },

  { id: "kernel", label: "Financial Kernel", icon: "chip", group: "system" },
  { id: "audit", label: "Audit Log", icon: "audit", group: "system" },
  { id: "console", label: "Console", icon: "term", group: "system" },
  { id: "settings", label: "Settings", icon: "gear", group: "system" },
];

const ROUTES = NAV.map((n) => n.id);

function Workspace({ id }: { id: string }) {
  switch (id) {
    case "deck":
      return <Deck />;
    case "portfolio":
      return <PortfolioPage />;
    case "orders":
      return <OrdersPage />;
    case "opportunities":
      return <OpportunitiesPage />;
    case "risk":
      return <RiskCenter />;
    case "approvals":
      return <ApprovalsPage />;
    case "agents":
      return <AgentsPage />;
    case "world":
      return <WorldPage />;
    case "knowledge":
      return <KnowledgePage />;
    case "calibration":
      return <CalibrationPage />;
    case "trace": {
      const q = window.location.hash.split("?")[1] ?? "";
      const initial = new URLSearchParams(q).get("id");
      return <TracePage initialId={initial} />;
    }
    case "kernel":
      return <KernelPage />;
    case "audit":
      return <AuditPage />;
    case "console":
      return <ConsolePage />;
    case "settings":
      return <SettingsPage />;
    default:
      return <Deck />;
  }
}

/**
 * Identity bootstrap: ask the SERVER whether a token is required.
 * - auth_required=false → enter immediately as the server's anonymous viewer.
 * - auth_required=true  → show the token gate until session/me succeeds.
 */
function useSession(): { loading: boolean; needToken: boolean } {
  const identity = useIdentity();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Try once with no credentials; the server decides.
      const res = await fetch("/api/v1/session/me").catch(() => null);
      if (cancelled) return;
      if (res && res.ok) {
        const data = (await res.json().catch(() => null)) as
          | { authenticated: boolean; auth_required?: boolean; operator_id?: string; role?: string }
          | null;
        if (data && (data.authenticated || data.auth_required === false)) {
          // Server resolved the identity (possibly the anonymous dev viewer).
          setIdentity({
            operatorId: data.operator_id || "anonymous",
            role: (data.role || "VIEWER") as Role,
            authenticated: true,
            token: "",
          });
        }
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Once a token is set and authenticated, we're in regardless of bootstrap.
  return { loading: loading && !identity.authenticated, needToken: !identity.authenticated };
}

export function App() {
  const { loading, needToken } = useSession();
  const identity = useIdentity();
  const [route, navigate] = useHashRoute(ROUTES);

  const submitToken = useCallback(
    async (token: string) => authenticateWithToken(token),
    [],
  );

  if (loading) {
    return (
      <div className="gate">
        <div className="gate-card">
          <div className="gate-logo">⬡</div>
          <h1 className="gate-title">AIOS-0X Terminal</h1>
          <p className="gate-sub">Resolving session…</p>
        </div>
      </div>
    );
  }

  if (needToken && !identity.authenticated) {
    return <TokenGate onSubmit={submitToken} />;
  }

  return (
    <Shell nav={NAV} current={route} onNav={navigate}>
      <Workspace id={route} />
    </Shell>
  );
}

function TokenGate({ onSubmit }: { onSubmit: (token: string) => Promise<boolean> }) {
  const [token, setToken] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const trySubmit = async () => {
    if (!token.trim()) return;
    setBusy(true);
    setErr("");
    const ok = await onSubmit(token.trim());
    setBusy(false);
    if (!ok) setErr("Authentication failed — check the token and try again.");
  };

  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-logo">⬡</div>
        <h1 className="gate-title">AIOS-0X Terminal</h1>
        <p className="gate-sub">The server requires an access token.</p>
        <input
          className="gate-input"
          type="password"
          placeholder="Bearer token"
          value={token}
          autoFocus
          disabled={busy}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void trySubmit();
          }}
        />
        {err && <p className="gate-err">{err}</p>}
        <button className="gate-btn" disabled={busy || !token.trim()} onClick={() => void trySubmit()}>
          {busy ? "Authenticating…" : "Enter Terminal"}
        </button>
      </div>
    </div>
  );
}
