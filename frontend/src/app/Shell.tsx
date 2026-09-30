/**
 * Application shell — system bar, icon rail, workspace router, mobile nav.
 * The system bar is always live: SSE status, autonomy, risk state, audit
 * integrity, and the UTC clock. A severe engine condition (audit chain
 * broken, emergency halt, lockout) renders a blocking banner — never hidden.
 */
import { useEffect, useState, type ReactNode } from "react";
import { onStream, type StreamStatus } from "../api/stream";
import type { Executive, Gates } from "../api/types";
import { ICONS, type NavItem } from "./nav";
import { agoLabel } from "../lib/format";
import { autonomyTone, riskTone } from "../lib/risk";
import { logout, useIdentity } from "../stores/identity";
import { useToasts } from "../stores/toasts";

function Icon({ path, size = 19 }: { path: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

function AutonomyChip({ mode }: { mode: string | null }) {
  const tone = autonomyTone(mode);
  const color = tone === "warn" ? "var(--warn)" : tone === "info" ? "var(--cyan)" : "var(--text-dim)";
  return (
    <span className="autonomy-chip" style={{ color, borderColor: "currentColor" }}>
      <Icon path={ICONS.shield} size={12} />
      {mode ?? "—"}
    </span>
  );
}

export function Shell({
  nav,
  current,
  onNavigate,
  children,
  executive,
  gates,
}: {
  nav: NavItem[];
  current: string;
  onNavigate: (id: string) => void;
  children: ReactNode;
  executive: Executive | null;
  gates: Gates | null;
}) {
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("offline");
  const [lastEvent, setLastEvent] = useState<number | null>(null);
  const [, tick] = useState(0);
  const identity = useIdentity();
  const toasts = useToasts();

  useEffect(() => {
    const off = onStream((s) => {
      setStreamStatus(s.status);
      setLastEvent(s.lastEventAt);
    });
    return off;
  }, []);

  // clock re-render every 30s
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 30_000);
    return () => window.clearInterval(t);
  }, []);

  const risk = executive?.emergency_state ?? null;
  const rTone = riskTone(risk);
  const chainOk = executive?.chain_valid !== false;
  const streamTone = streamStatus === "live" ? "ok" : streamStatus === "offline" ? "dim" : "warn";
  const streamLabel =
    streamStatus === "live"
      ? `LIVE · ${agoLabel(lastEvent)}`
      : streamStatus === "connecting"
        ? "CONNECTING…"
        : streamStatus === "reconnecting"
          ? "RECONNECTING…"
          : "OFFLINE";

  const severe: string[] = [];
  if (executive && !executive.chain_valid) severe.push("Audit hash-chain integrity FAILURE — decisions after this point are not provable. Stop and repair before trusting data.");
  if (risk && ["EMERGENCY_HALT", "LOCKOUT"].includes(risk.toUpperCase())) severe.push(`Risk governor state: ${risk}. Execution is firewalled.`);
  if (gates && !gates.production_allowed && gates.autonomy === "AUTONOMOUS") {
    severe.push("AUTONOMOUS mode active while production gates are incomplete — this violates the deployment constitution. Reduce to SUPERVISED.");
  }

  return (
    <div className="app">
      <header className="sysbar">
        <span className="logo">
          AIOS-0X <small>V0.8.2-SECURE</small>
        </span>
        <span className={`ind hide-sm`} style={{ color: chainOk ? "var(--ok)" : "var(--bad)" }}>
          {chainOk ? "ALL SYSTEMS NOMINAL" : "CHAIN INTEGRITY FAIL"}
        </span>
        <span className="ind hide-sm" style={{ color: rTone === "ok" ? "var(--ok)" : rTone === "bad" ? "var(--bad)" : "var(--warn)" }}>
          RISK: {risk?.toUpperCase() ?? "—"}
        </span>
        <span className="spacer" />
        <AutonomyChip mode={gates?.autonomy ?? null} />
        <span className="ind" style={{ color: streamTone === "ok" ? "var(--ok)" : streamTone === "warn" ? "var(--warn)" : "var(--text-faint)" }}>
          {streamLabel}
        </span>
        <span className="muted hide-sm">
          {identity.operatorId} · {identity.role}
        </span>
        <button
          type="button"
          onClick={logout}
          style={{
            background: "transparent",
            border: "1px solid var(--hairline-2)",
            color: "var(--text-dim)",
            borderRadius: 4,
            fontSize: 11,
            padding: "3px 8px",
            cursor: "pointer",
            fontFamily: "var(--font-ui)",
          }}
          title="Sign out"
        >
          SIGN OUT
        </button>
      </header>

      {severe.length > 0 && (
        <div
          role="alert"
          style={{
            background: "var(--bad-bg)",
            borderBottom: "1px solid rgba(255,23,68,0.4)",
            color: "var(--text)",
            padding: "8px 14px",
            fontSize: 12.5,
            fontWeight: 600,
          }}
        >
          {severe.map((s) => (
            <div key={s}>⚠ {s}</div>
          ))}
        </div>
      )}

      <div className="body">
        <nav className="rail" aria-label="Workspaces">
          {nav.map((item, i) => (
            <span key={item.id} style={{ display: "contents" }}>
              {(i === 3 || i === 10 || i === 16) && <span className="sep" />}
              <button
                type="button"
                data-label={item.label}
                className={current === item.id ? "active" : ""}
                onClick={() => onNavigate(item.id)}
                aria-current={current === item.id ? "page" : undefined}
              >
                <Icon path={item.icon} />
              </button>
            </span>
          ))}
        </nav>
        <main className="workspace" id="main">
          {children}
        </main>
      </div>

      <nav className="mobilenav" aria-label="Workspaces (mobile)">
        {nav.slice(0, 8).map((item) => (
          <button
            key={item.id}
            type="button"
            className={current === item.id ? "active" : ""}
            onClick={() => onNavigate(item.id)}
          >
            <Icon path={item.icon} size={17} />
            <span className="lbl">{item.label.split(" ")[0]}</span>
          </button>
        ))}
      </nav>

      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <div className="t">{t.title}</div>
            {t.detail ? <div className="dim">{t.detail}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
