/**
 * Settings workspace: AI provider, data sources, risk limits, execution rails,
 * autonomy, session identity. Every visual indicator reflects real backend
 * state — secrets are NEVER shown.
 *
 * SECURITY: Role and operator_id are server-resolved and displayed read-only.
 * Token is managed by the login gate and not editable here.
 */
import { useState } from "react";
import { settingsApi } from "../../api/endpoints";
import { ErrorBox, KV, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useIdentity } from "../../stores/identity";
import { runControl } from "../../lib/control";

function ProviderBadge({ configured, name }: { configured: boolean; name: string }) {
  return (
    <KV
      k={name}
      v={<Pill tone={configured ? "ok" : "warn"}>{configured ? "configured" : "missing"}</Pill>}
    />
  );
}

export function SettingsPage() {
  const settings = useApi(() => settingsApi.settings());
  const s = settings.data;
  const identity = useIdentity();
  const [confirmLive, setConfirmLive] = useState(false);

  if (settings.error) return <ErrorBox title="Settings unavailable" detail={settings.error} />;

  return (
    <>
      <div className="pagehead">
        <h1>Settings</h1>
        <span className="sub">Backend-reported configuration status — never reveals secrets</span>
      </div>

      <div className="grid cols-2" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Authenticated Session">
          <KV k="Operator ID" v={<span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{identity.operatorId || "—"}</span>} />
          <KV k="Role (server-assigned)" v={<Pill tone="ok">{identity.role}</Pill>} />
          <KV k="Token status" v={<Pill tone={identity.token ? "ok" : "warn"}>{identity.token ? "active (session-only)" : "not set"}</Pill>} />
          <div className="dim" style={{ fontSize: 11, marginTop: 8 }}>
            Identity is resolved by the server from your bearer token. Role and operator ID cannot be changed from the browser.
          </div>
        </Panel>

        <Panel title="AI / Model Configuration">
          <KV k="Model provider" v={s?.system.model_provider ?? "—"} />
          <KV k="Research mode" v={<Pill tone={s?.system.research_mode === "deterministic" ? "dim" : "ok"}>{s?.system.research_mode ?? "—"}</Pill>} />
          <KV k="LLM configured" v={<Pill tone={s?.system.llm_configured ? "ok" : "warn"}>{s?.system.llm_configured ? "yes" : "no — deterministic mode"}</Pill>} />
          <KV k="Shadow mode" v={<Pill tone={s?.system.shadow_mode ? "info" : "dim"}>{s?.system.shadow_mode ? "YES (paper only)" : "off"}</Pill>} />
          <div style={{ marginTop: 8 }}>
            <ProviderBadge configured={!!s?.ai.research_model_cheap} name={`Cheap model: ${s?.ai.research_model_cheap ?? "—"}`} />
            <ProviderBadge configured={!!s?.ai.research_model_reasoning} name={`Reasoning model: ${s?.ai.research_model_reasoning ?? "—"}`} />
            <ProviderBadge configured={!!s?.ai.verification_model} name={`Verification model: ${s?.ai.verification_model ?? "—"}`} />
            <KV k="Temperature" v={s?.ai.llm_temperature !== null && s?.ai.llm_temperature !== undefined ? String(s.ai.llm_temperature) : "—"} />
          </div>
        </Panel>
      </div>

      <div className="grid cols-2" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Data Providers">
          <ProviderBadge configured={!!s?.data.finnhub} name="Finnhub" />
          <ProviderBadge configured={!!s?.data.gnews} name="GNews" />
          <ProviderBadge configured={!!s?.data.newsdata} name="NewsData" />
          <ProviderBadge configured={!!s?.data.marketstack} name="MarketStack" />
          <ProviderBadge configured={!!s?.data.fred} name="FRED" />
        </Panel>

        <Panel title="Risk Limits (governor)">
          <KV k="Max class exposure" v={s?.risk.max_class_exposure_pct !== null && s?.risk.max_class_exposure_pct !== undefined ? `${s.risk.max_class_exposure_pct}%` : "—"} />
          <KV k="Halt drawdown" v={s?.risk.halt_dd_pct !== null && s?.risk.halt_dd_pct !== undefined ? `${s.risk.halt_dd_pct}%` : "—"} />
          <KV k="Warning drawdown" v={s?.risk.warning_dd_pct !== null && s?.risk.warning_dd_pct !== undefined ? `${s.risk.warning_dd_pct}%` : "—"} />
          <KV k="Caution drawdown" v={s?.risk.caution_dd_pct !== null && s?.risk.caution_dd_pct !== undefined ? `${s.risk.caution_dd_pct}%` : "—"} />
        </Panel>
      </div>

      <div className="grid cols-2">
        <Panel title="Execution Rails">
          <KV k="Live execution allowed (env)" v={<Pill tone={s?.execution_rails.live_execution_allowed_env ? "warn" : "ok"}>{s?.execution_rails.live_execution_allowed_env ? "YES" : "no (paper only)"}</Pill>} />
          <KV k="Micro-live cap" v={s?.execution_rails.micro_live_cap_usd !== null && s?.execution_rails.micro_live_cap_usd !== undefined ? `$${s.execution_rails.micro_live_cap_usd}` : "—"} />
          <KV k="Constitution pinned" v={<Pill tone={s?.execution_rails.constitution_pinned ? "ok" : "bad"}>{s?.execution_rails.constitution_pinned ? "YES" : "no"}</Pill>} />
        </Panel>

        <Panel title="Live Capital Approval (ADMIN gate)">
          <p className="dim" style={{ marginTop: 0, fontSize: 12.5 }}>
            The engine cannot self-approve live capital. A human with ADMIN authority must click below; the action is permanently audited.
          </p>
          <button className="btn danger" type="button" onClick={() => setConfirmLive(true)}>
            Approve live capital — admin-only, audited
          </button>
          {confirmLive && (
            <div style={{ marginTop: 8 }}>
              <p style={{ color: "var(--bad)", fontWeight: 700, margin: "0 0 8px" }}>
                This authorizes real capital deployment. Are you sure?
              </p>
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn danger" type="button" onClick={async () => {
                  await runControl("approve_live_capital", { note: "UI settings approve" });
                  setConfirmLive(false);
                }}>CONFIRM — approve live capital</button>
                <button className="btn" type="button" onClick={() => setConfirmLive(false)}>Cancel</button>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
