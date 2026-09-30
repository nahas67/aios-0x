/**
 * Operator Console: natural-language query and command interface.
 * Queries are read-only and return real engine state; commands execute
 * through the RBAC-enforced audited control plane.
 *
 * Interaction model:
 *  - Informational query → answer + data
 *  - Proposed action → clearly labelled, requires confirm
 *  - Authorized action → audited, result shown
 *  - Denied action → clear reason, denial recorded
 *  - Failed action → error surfaced
 */
import { useRef, useState } from "react";
import { controlApi } from "../../api/endpoints";
import { Panel } from "../../components/ui";
import { useIdentity } from "../../stores/identity";
import { pushToast } from "../../stores/toasts";

interface Message {
  role: "user" | "assistant";
  content: string;
  detail?: unknown;
  kind?: string;
  ts: number;
}

export function ConsolePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const identity = useIdentity();
  const endRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text, ts: Date.now() }]);
    setBusy(true);
    try {
      const res = await controlApi.chat({
        operator_id: identity.operatorId || "console",
        role: identity.role,
        message: text,
      });
      const answer = res.answer ?? "No answer";
      const detail = res.data ?? res.result ?? null;
      setMessages((prev) => [...prev, { role: "assistant", content: answer, detail, kind: res.kind, ts: Date.now() }]);
      if (res.kind === "error" || res.kind === "denied") {
        pushToast(res.kind === "error" ? "bad" : "warn", res.kind.toUpperCase(), answer);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${msg}`, ts: Date.now(), kind: "error" }]);
      pushToast("bad", "Console error", msg);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <>
      <div className="pagehead">
        <h1>Operator Console</h1>
        <span className="sub">
          Ask about P&L, gates, hypotheses, models, risk, or issue commands. All actions audited.
        </span>
      </div>
      <Panel title={`Session · ${identity.role} · ${identity.operatorId}`}>
        <div
          style={{
            maxHeight: 420,
            overflowY: "auto",
            padding: "8px 0",
            borderBottom: "1px solid var(--hairline)",
            marginBottom: 12,
          }}
        >
          {messages.length === 0 && (
            <div className="empty">
              Try: "show P&L", "what gates are open?", "show risk state", "pause trading"
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span
                  style={{
                    fontWeight: 700,
                    fontSize: 11,
                    color: m.role === "user" ? "var(--cyan)" : "var(--green)",
                  }}
                >
                  {m.role === "user" ? identity.operatorId : "AIOS"}
                </span>
                <span className="dim" style={{ fontSize: 10 }}>
                  {new Date(m.ts).toLocaleTimeString([], { hour12: false })}
                </span>
                {m.kind && m.kind !== "query" && m.kind !== "command" && (
                  <span className="pill" style={{ fontSize: 9, padding: "1px 5px" }}>
                    {m.kind}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 13, marginTop: 2, whiteSpace: "pre-wrap" }}>{m.content}</div>
              {m.detail != null && (
                <details style={{ marginTop: 4 }}>
                  <summary style={{ fontSize: 11, color: "var(--text-dim)", cursor: "pointer" }}>
                    show data
                  </summary>
                  <pre className="code" style={{ marginTop: 4, fontSize: 10.5 }}>
                    {typeof m.detail === "string" ? m.detail : JSON.stringify(m.detail ?? null, null, 2) ?? "null"}
                  </pre>
                </details>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
            placeholder="Ask about P&L, risk, gates, models, or issue a command…"
            style={{
              flex: 1,
              background: "var(--inset)",
              border: "1px solid var(--hairline-2)",
              color: "var(--text)",
              borderRadius: 6,
              padding: "8px 10px",
              fontSize: 13,
              fontFamily: "var(--font-ui)",
            }}
            disabled={busy}
          />
          <button className="btn primary" type="button" onClick={send} disabled={busy || !input.trim()}>
            {busy ? "…" : "Send"}
          </button>
        </div>
      </Panel>
    </>
  );
}
