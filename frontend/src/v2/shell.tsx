/**
 * V2 shell: system bar, icon rail, command palette, toasts, identity gate.
 *
 * Benchmark practices baked in:
 * - Always-live system bar (stream, chain integrity, risk state, autonomy, clock)
 * - Command palette (⌘K / Ctrl+K) — Bloomberg-style keyboard workflow
 * - Severe conditions (broken audit chain, emergency halt, lockout) render a
 *   blocking banner that navigation can never hide
 * - Identity resolved by the SERVER; when no token is configured the server
 *   answers session/me anonymously and the UI enters directly (no fake login)
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { executiveApi, type Executive } from "./api";
import { fmt, Icon, toneFor, type IconName } from "./kit";
import { onStream, startStream, stopStream, type StreamStatus } from "../api/stream";
import { logout, useIdentity } from "../stores/identity";
import { pushToast, useToasts } from "../stores/toasts";

/* ------------------------------------------------------------------ types */

export interface NavDef {
  id: string;
  label: string;
  icon: IconName;
  group: string;
}

/* ---------------------------------------------------------------- palette */

function Palette({ nav, onNav, onClose }: { nav: NavDef[]; onNav: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => inputRef.current?.focus(), []);

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return nav.filter(
      (n) => !needle || n.label.toLowerCase().includes(needle) || n.id.includes(needle) || n.group.includes(needle),
    );
  }, [nav, q]);

  useEffect(() => setSel(0), [q]);

  const commit = useCallback(
    (i: number) => {
      const it = items[i];
      if (it) onNav(it.id);
      onClose();
    },
    [items, onNav, onClose],
  );

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(items.length - 1, s + 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
      else if (e.key === "Enter") { e.preventDefault(); commit(sel); }
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [items, sel, commit, onClose]);

  return (
    <div className="palveil" onMouseDown={onClose}>
      <div className="pal" onMouseDown={(e) => e.stopPropagation()}>
        <input ref={inputRef} placeholder="Jump to workspace…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="pal-list">
          {items.map((it, i) => (
            <div key={it.id} className={`pal-item${i === sel ? " on" : ""}`} onMouseEnter={() => setSel(i)} onClick={() => commit(i)}>
              <Icon name={it.icon} size={15} />
              {it.label}
              <span className="grp">{it.group}</span>
            </div>
          ))}
          {items.length === 0 && <div className="empty">No matching workspace.</div>}
        </div>
        <div className="pal-hint">↑↓ navigate · ⏎ open · esc close</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ shell */

function Toasts() {
  const toasts = useToasts();
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <div className="t">{t.title}</div>
          {t.detail && <div className="d">{t.detail}</div>}
        </div>
      ))}
    </div>
  );
}

const GROUPS = ["trade", "safety", "intel", "research", "finance", "system"] as const;

export function Shell({
  nav,
  current,
  onNav,
  children,
}: {
  nav: NavDef[];
  current: string;
  onNav: (id: string) => void;
  children: ReactNode;
}) {
  const [stream, setStream] = useState<StreamStatus>("offline");
  const [lastEvent, setLastEvent] = useState<number | null>(null);
  const [, tick] = useState(0);
  const [palOpen, setPalOpen] = useState(false);
  const identity = useIdentity();
  const [exec, setExec] = useState<Pick<Executive, "chain_valid" | "emergency_state"> | null>(null);
  const [auto, setAuto] = useState<string | null>(null);

  useEffect(() => {
    startStream();
    const off = onStream((s) => {
      setStream(s.status);
      setLastEvent(s.lastEventAt);
      if (s.frame?.executive) {
        setExec(s.frame.executive);
        setAuto(null);
      }
    });
    const t = window.setInterval(() => tick((n) => n + 1), 30_000);
    // autonomy lives in /gates, fetched periodically (not in the SSE frame)
    const g = window.setInterval(() => {
      executiveApi
        .gates()
        .then((x) => setAuto(x.autonomy ?? null))
        .catch(() => undefined);
    }, 30_000);
    executiveApi
      .gates()
      .then((x) => setAuto(x.autonomy ?? null))
      .catch(() => undefined);
    return () => {
      off();
      stopStream();
      window.clearInterval(t);
      window.clearInterval(g);
    };
  }, []);

  // ⌘K / Ctrl+K palette
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const chainOk = exec ? exec.chain_valid !== false : true;
  const risk = exec?.emergency_state ?? null;
  const riskTone = risk && ["EMERGENCY_HALT", "LOCKOUT"].includes(risk.toUpperCase()) ? "bad" : "ok";
  const streamTone = stream === "live" ? "ok" : stream === "offline" ? "dim" : "warn";
  const streamLabel =
    stream === "live" ? "LIVE" : stream === "connecting" ? "CONNECTING" : stream === "reconnecting" ? "RETRYING" : "OFFLINE";

  const severe: string[] = [];
  if (exec && !exec.chain_valid)
    severe.push(
      "Audit hash-chain integrity FAILURE — decisions after this point are not provable. Stop and repair before trusting any data.",
    );
  if (risk && ["EMERGENCY_HALT", "LOCKOUT"].includes(risk.toUpperCase()))
    severe.push(`Risk governor state: ${risk}. Execution is firewalled.`);

  const groups = GROUPS.map((g) => ({ g, items: nav.filter((n) => n.group === g) })).filter((x) => x.items.length > 0);
  const clock = new Date().toISOString().slice(11, 19) + "Z";

  return (
    <div className="term">
      <header className="sysbar">
        <span className="brand">
          AIOS-0X <small>TERMINAL</small>
        </span>
        <span className="ind hide-sm" style={{ color: chainOk ? "var(--ok)" : "var(--bad)" }}>
          <span className={`dot ${chainOk ? "ok" : "bad"}`} /> {chainOk ? "CHAIN VALID" : "CHAIN FAIL"}
        </span>
        <span className="ind hide-sm" style={{ color: riskTone === "bad" ? "var(--bad)" : "var(--ok)" }}>
          <span className={`dot ${riskTone === "bad" ? "bad" : "ok"}`} /> RISK {risk ? risk.toUpperCase() : "NORMAL"}
        </span>
        {auto && (
          <span className="ind hide-sm" style={{ color: auto === "AUTONOMOUS" ? "var(--warn)" : "var(--cyan)" }}>
            <span className={`dot ${toneFor(auto) === "warn" ? "warn" : ""}`} /> {auto}
          </span>
        )}
        <span className="spacer" />
        <button className="rail-cmd" style={{ marginTop: 0, width: "auto", padding: "0 12px", height: 26 }} onClick={() => setPalOpen(true)}>
          ⌘K
        </button>
        <span className="ind" style={{ color: streamTone === "ok" ? "var(--ok)" : streamTone === "warn" ? "var(--warn)" : "var(--faint)" }}>
          <span className={`dot ${streamTone}${stream === "live" ? " live" : ""}`} /> {streamLabel}
          {lastEvent ? ` · ${fmt.ago(new Date(lastEvent).toISOString())}` : ""}
        </span>
        <span className="clock ind hide-sm">{clock}</span>
        <button
          className="idchip"
          title="Identity is resolved by the server. Click to sign out."
          onClick={() => {
            logout();
            pushToast("info", "Signed out", "Session token cleared.");
            window.location.reload();
          }}
        >
          <span className={`dot ${identity.authenticated ? "ok" : "warn"}`} />
          {identity.operatorId || "anonymous"}
          <span className={`rolepill role-${identity.role}`}>{identity.role}</span>
        </button>
      </header>

      <div className="term-body">
        <nav className="rail">
          {groups.map(({ g, items }, gi) => (
            <div key={g} className="rail-group" style={gi > 0 ? { marginTop: 8 } : undefined}>
              {gi > 0 && <div className="rail-sep" />}
              {items.map((n) => (
                <button
                  key={n.id}
                  className={`rbtn${current === n.id ? " on" : ""}`}
                  title={n.label}
                  aria-label={n.label}
                  onClick={() => onNav(n.id)}
                >
                  <Icon name={n.icon} />
                </button>
              ))}
            </div>
          ))}
          <button className="rail-cmd" title="Command palette (⌘K)" onClick={() => setPalOpen(true)}>
            ⌘
          </button>
        </nav>

        <main className="main">
          {severe.map((s, i) => (
            <div key={i} className="severe">
              <b>⚠ SEVERE — </b>
              {s}
            </div>
          ))}
          {children}
        </main>
      </div>

      {palOpen && <Palette nav={nav} onNav={onNav} onClose={() => setPalOpen(false)} />}
      <Toasts />
    </div>
  );
}

export function useHashRoute(valid: string[]): [string, (id: string) => void] {
  const parse = useCallback(() => {
    const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0] || valid[0];
    return valid.includes(raw) ? raw : valid[0];
  }, [valid]);
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const h = () => setRoute(parse());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, [parse]);
  const navigate = useCallback((id: string) => {
    window.location.hash = `/${id}`;
    window.scrollTo(0, 0);
  }, []);
  return [route, navigate];
}
