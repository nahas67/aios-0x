import React, { useState, useEffect } from 'react';
import {
  Sliders,
  ShieldCheck,
  AlertTriangle,
  BrainCircuit,
  Zap,
  BarChart2,
  ReceiptText,
  Bell,
  Monitor,
  Key,
  Check,
  Copy,
  Download,
  Upload,
  RotateCcw,
  Save,
  Lock,
  Radio,
  Fingerprint,
  LineChart,
} from 'lucide-react';
import { SystemSettings, AutonomyLevel } from '../../types';
import {
  ACCENTS,
  THEMES,
  applyAccent,
  applyTheme,
  readStoredAccent,
  readStoredTheme,
  type AccentName,
  type ThemeName,
} from '../../lib/theme';
import LayoutPanel from '../LayoutPanel';
import { WORKSPACE_TABS } from '../../types';
import type { WorkspaceLayout } from '../../lib/layout';
import type { WorkspaceTab } from '../../types';

/**
 * Accent and theme labels, keyed by the `lib/theme` union.
 *
 * Both lists are DERIVED from `ACCENTS` / `THEMES`, and the metadata is a `Record` over
 * those same unions. That combination is what prevents drift in both directions: adding an
 * accent to `lib/theme.ts` and forgetting it here is a compile error (the `Record` is no
 * longer exhaustive), and the picker cannot offer an option with no label because it is
 * built from the same list.
 *
 * The old inline array inferred `id: string`, which is why the click handler needed
 * `as any` to satisfy the settings union. Typing `id` as `AccentName` removes the cast and
 * turns a typo into a compile error instead of a swatch that selects nothing.
 */
const ACCENT_META: Record<AccentName, { name: string; desc: string }> = {
  CYAN: { name: 'Signature Cyan', desc: 'AIOS-0X default' },
  EMERALD: { name: 'Terminal Emerald', desc: 'High-contrast green' },
  AMBER: { name: 'Gold & Amber', desc: 'Fixed income terminal' },
  VIOLET: { name: 'Deep Violet', desc: 'Macro sovereign' },
};

const ACCENT_PRESETS = ACCENTS.map((id) => ({ id, ...ACCENT_META[id] }));

const THEME_NAMES: Record<ThemeName, string> = {
  'dark-oled': 'OLED Dark',
  paper: 'Paper Light',
};

const THEME_LABELS = THEMES.map((id) => ({ id, name: THEME_NAMES[id] }));

interface SettingsWorkspaceProps {
  settings: SystemSettings;
  /** Which workspace is open, so the layout editor can warn before you hide it. */
  activeTab: WorkspaceTab;
  /** Presentation only: reorder and hide. Cannot affect what the backend enforces. */
  onLayoutChange: (next: WorkspaceLayout) => void;
  serverVersion: number | null;
  serverAvailable: boolean;
  serverReason: string | null;
  onSaveSettings: (
    next: SystemSettings,
  ) => Promise<{ ok: true; version: number } | { ok: false; reason: string; authRequired: boolean }>;
  onResetDefaults: () => void;
  onTriggerToast: (msg: string) => void;
}

type SettingsSection = 
  | 'autonomy'
  | 'risk'
  | 'agents'
  | 'execution'
  | 'tradingview'
  | 'oracles'
  | 'backtest'
  | 'accounting'
  | 'apikeys'
  | 'alerts'
  | 'display'
  | 'security'
  | 'backup';

export const SettingsWorkspace: React.FC<SettingsWorkspaceProps> = ({
  settings,
  serverVersion,
  serverAvailable,
  serverReason,
  activeTab,
  onLayoutChange,
  onSaveSettings,
  onResetDefaults,
  onTriggerToast,
}) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('autonomy');
  const [formState, setFormState] = useState<SystemSettings>(settings);
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [authBlocked, setAuthBlocked] = useState<boolean>(false);
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);

  // The server blob wins whenever it arrives (initial GET resolves after
  // mount); local edits are applied on top and never clobbered by renders.
  const syncedRef = React.useRef(settings);
  useEffect(() => {
    if (syncedRef.current !== settings) {
      syncedRef.current = settings;
      setFormState(settings);
      setIsDirty(false);
    }
  });

  const handleChange = <K extends keyof SystemSettings>(key: K, value: SystemSettings[K]) => {
    setFormState(prev => {
      const next = { ...prev, [key]: value };
      setIsDirty(true);
      return next;
    });
  };

  const handleVenueToggle = (venueId: string, enabled: boolean) => {
    setFormState(prev => {
      const nextVenues = prev.venues.map(v => v.id === venueId ? { ...v, enabled } : v);
      setIsDirty(true);
      return { ...prev, venues: nextVenues };
    });
  };

  /**
   * APPEARANCE IS CLIENT-LOCAL, NOT A SERVER SETTING.
   *
   * `accentTheme` used to live on `SystemSettings`, which meant clicking a swatch marked
   * the form dirty and armed a Save button — for a change that was already visible and
   * that the server had never heard of. The setting round-tripped through a PUT the
   * backend does not define, so "unsaved changes" was a lie in both directions.
   *
   * Theme and accent are now applied immediately and kept in localStorage (see
   * `lib/theme.ts`). They are presentation, they are not policy, and they do not belong in
   * a payload the server validates. `lib/theme.ts` owns both axes.
   */
  const [theme, setTheme] = useState<ThemeName>(() => readStoredTheme());
  const [accent, setAccent] = useState<AccentName>(() => readStoredAccent());

  const chooseTheme = (next: ThemeName) => {
    setTheme(next);
    applyTheme(next);
  };

  const chooseAccent = (next: AccentName) => {
    setAccent(next);
    applyAccent(next);
  };

  const handleSave = async () => {
    if (isSaving) return;
    setIsSaving(true);
    setSaveError(null);
    setAuthBlocked(false);
    const result = await onSaveSettings(formState);
    setIsSaving(false);
    if (result.ok) {
      setIsDirty(false);
      onTriggerToast(`System configuration persisted server-side (settings v${result.version}).`);
    } else {
      setSaveError(result.reason);
      setAuthBlocked(result.authRequired);
      onTriggerToast(
        result.authRequired
          ? 'Save blocked: operator token required (PUT /api/v1/settings/v1 answered 401).'
          : `Save failed: ${result.reason}`,
      );
    }
  };

  const handleRevert = () => {
    setFormState(settings);
    setIsDirty(false);
    setSaveError(null);
    onTriggerToast('Settings reverted to the last server state.');
  };

  const handleExportConfig = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(formState, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `aios0x_config_${new Date().toISOString().slice(0,10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    onTriggerToast('System configuration exported to JSON file.');
  };

  const handleImportConfigFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);
        if (parsed && typeof parsed === 'object' && parsed.autonomyLevel) {
          setFormState(parsed);
          setIsDirty(true);
          onTriggerToast('Configuration imported successfully from JSON file. Click SAVE to persist server-side.');
        } else {
          onTriggerToast('Error: JSON file does not match institutional SystemSettings schema.');
        }
      } catch (err) {
        void err;
        onTriggerToast('Failed to parse uploaded JSON file.');
      }
    };
    reader.readAsText(file);
  };

  const navItems: { id: SettingsSection; label: string; icon: React.ElementType; badge?: string }[] = [
    { id: 'autonomy', label: 'Autonomy & Governance', icon: Sliders },
    { id: 'risk', label: 'Risk Limits & Firewall', icon: ShieldCheck, badge: 'Constitution' },
    { id: 'agents', label: 'Multi-Agent & LLM Engines', icon: BrainCircuit },
    { id: 'execution', label: 'Execution & Venues', icon: Zap, badge: `${formState.venues.length} Venues` },
    { id: 'tradingview', label: 'TradingView & Chart API', icon: BarChart2 },
    { id: 'oracles', label: 'Data Feeds & Oracles', icon: Radio },
    { id: 'backtest', label: 'Stress Testing & Monte Carlo', icon: LineChart, badge: 'Monte Carlo' },
    { id: 'accounting', label: 'Accounting & Controller', icon: ReceiptText, badge: 'Compliance' },
    { id: 'apikeys', label: 'API Keys & Secrets Vault', icon: Key },
    { id: 'alerts', label: 'Alerts, Webhooks & Telegram', icon: Bell },
    { id: 'display', label: 'Display & UI Preferences', icon: Monitor },
    { id: 'security', label: 'Security & Multi-Sig', icon: Lock },
    { id: 'backup', label: 'Backup, Export & Reset', icon: Download },
  ];

  return (
    <div className="space-y-4 pb-16 font-mono text-xs">
      {/* Workspace Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              INSTITUTIONAL SETTINGS & SYSTEM CONFIGURATION
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
              MASTER CONTROL
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Operational Constitution • Risk Governance • Multi-Agent LLMs • Smart Order Routing • Cryptographic Enforcers
          </div>
        </div>

        {/* Global Save / Revert Bar (server is source of truth) */}
        <div className="flex items-center gap-2.5">
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-sunken border border-border-subtle text-text-muted">
            <Fingerprint className="w-3.5 h-3.5 text-accent" />
            <span className="text-[10px]">SETTINGS: <span className="text-accent font-mono">{serverAvailable && serverVersion !== null ? `v${serverVersion} (server)` : 'server plane unwired'}</span></span>
          </div>

          {isDirty && (
            <button
              onClick={handleRevert}
              className="px-3 py-1.5 rounded bg-surface-veil hover:bg-surface-raised text-text hover:text-text-strong transition-colors flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>REVERT</span>
            </button>
          )}

          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving || !serverAvailable}
            title={!serverAvailable ? (serverReason ?? 'settings plane not wired') : undefined}
            className={`px-4 py-1.5 rounded font-bold transition-all flex items-center gap-1.5 ${
              isDirty && serverAvailable && !isSaving
                ? 'bg-accent hover:bg-accent text-text-strong shadow-[0_0_16px_rgba(0,240,255,0.4)] animate-pulse'
                : 'bg-surface-raised text-text-subtle border border-border-strong cursor-not-allowed'
            }`}
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isSaving ? 'PERSISTING…' : isDirty ? (serverAvailable ? 'SAVE TO SERVER' : 'SAVE UNAVAILABLE') : 'CONFIG SYNCED'}</span>
          </button>
        </div>
      </div>

      {!serverAvailable && (
        <div className="p-3 rounded bg-warning-bg border border-warning text-warning text-xs">
          Settings plane unwired: {serverReason ?? 'no reason published'}. The form below shows neutral
          defaults — edits are held locally and cannot persist until the plane is wired.
        </div>
      )}
      {authBlocked && (
        <div className="p-3 rounded bg-destructive-bg border border-destructive text-destructive text-xs">
          Operator token required: PUT /api/v1/settings/v1 answered 401. Set your bearer token via the
          identity control (client.ts) and retry — edits are kept, nothing was saved.
        </div>
      )}
      {saveError && !authBlocked && (
        <div className="p-3 rounded bg-destructive-bg border border-destructive text-destructive text-xs">
          Save failed: {saveError}
        </div>
      )}

      {/* Main Split Layout: Left Settings Nav + Right Setting Pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Settings Navigation Column */}
        <div className="lg:col-span-3 bg-[var(--color-surface-1)] border border-border-strong rounded-md p-2 shadow-2xl space-y-1">
          <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-text-muted border-b border-border-subtle mb-1 flex items-center justify-between">
            <span>Modules</span>
            <span className="text-[9px] text-accent">{navItems.length} Sections</span>
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded transition-all text-left group ${
                  isActive
                    ? 'bg-info-bg text-accent border border-accent shadow-[0_0_12px_rgba(0,240,255,0.15)] font-semibold'
                    : 'text-text-muted hover:text-text-strong hover:bg-surface-veil border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-accent' : 'text-text-muted group-hover:text-text'}`} />
                  <span className="text-xs">{item.label}</span>
                </div>
                {item.badge && (
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-surface-sunken text-text-muted border border-border-subtle">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}

          <div className="pt-3 mt-3 border-t border-border-subtle px-2 text-[10px] text-text-muted space-y-1">
            <div className="flex justify-between">
              <span>SERVER VERSION:</span>
              <strong className="text-text">{serverAvailable && serverVersion !== null ? `v${serverVersion}` : '—'}</strong>
            </div>
            <div className="flex justify-between">
              <span>UNSaved EDITS:</span>
              <strong className={isDirty ? 'text-warning' : 'text-text-subtle'}>{isDirty ? 'YES' : 'NO'}</strong>
            </div>
          </div>
        </div>

        {/* Settings Detail Pane */}
        <div className="lg:col-span-9 space-y-4">
          
          {/* SECTION 1: Autonomy & Governance */}
          {activeSection === 'autonomy' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-accent" />
                    AUTONOMY LEVEL, EXECUTION MODE & SCHEDULE GOVERNANCE
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Define the execution authorization boundaries for multi-agent trading models.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-info-bg text-accent border border-accent">
                  CURRENT: {formState.autonomyLevel}
                </span>
              </div>

              {/* Autonomy Level Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  {
                    level: 'MANUAL',
                    title: 'Manual Execution Only',
                    desc: 'Agents generate signals and debates, but all orders require explicit human authorization before dispatch.',
                    badge: 'Zero Automation',
                  },
                  {
                    level: 'ASSISTED',
                    title: 'Assisted Automation',
                    desc: 'Small rebalancing slices auto-executed under $100k; all major position openings require human ratification.',
                    badge: 'Micro-Orders Auto',
                  },
                  {
                    level: 'SUPERVISED',
                    title: 'Supervised Autonomy (Recommended)',
                    desc: 'Full autonomous trading within strict Risk Firewall bounds. Halts on anomalies or risk breaches.',
                    badge: 'Active Production',
                  },
                  {
                    level: 'AUTONOMOUS',
                    title: 'Full Autonomous Operation',
                    desc: 'End-to-end autonomous decision, debate synthesis, and SOR dispatch without human-in-the-loop delay.',
                    badge: 'High Velocity',
                  },
                ].map((item) => {
                  const isSelected = formState.autonomyLevel === item.level;
                  return (
                    <div
                      key={item.level}
                      onClick={() => handleChange('autonomyLevel', item.level as AutonomyLevel)}
                      className={`p-3.5 rounded border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-info-bg border-accent text-text-strong shadow-[0_0_16px_rgba(0,240,255,0.15)]'
                          : 'bg-surface-veil border-border-subtle text-text hover:bg-surface-veil'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <div className={`w-3 h-3 rounded-full border flex items-center justify-center ${isSelected ? 'border-accent bg-accent' : 'border-border-subtle'}`}>
                            {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-accent" />}
                          </div>
                          <span className="font-bold text-xs">{item.title}</span>
                        </div>
                        <span className="text-[9px] font-mono px-1 rounded bg-surface-sunken border border-border-strong text-text-muted">
                          {item.badge}
                        </span>
                      </div>
                      <p className="text-[11px] text-text-muted pl-5 leading-relaxed">
                        {item.desc}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Execution Mode & Trading Windows */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Default Execution Mode</div>
                    <div className="text-text-muted text-[11px]">Toggle between simulated paper sandbox and live exchange gateways.</div>
                  </div>
                  <div className="flex items-center gap-2 bg-surface-deep p-1 rounded border border-border-strong">
                    <button
                      onClick={() => handleChange('defaultExecutionMode', 'PAPER')}
                      className={`flex-1 py-1 rounded transition-colors text-xs font-mono ${
                        formState.defaultExecutionMode === 'PAPER'
                          ? 'bg-info-bg text-accent border border-accent font-bold'
                          : 'text-text-muted hover:text-text-strong'
                      }`}
                    >
                      PAPER SIMULATION
                    </button>
                    <button
                      onClick={() => handleChange('defaultExecutionMode', 'LIVE')}
                      className={`flex-1 py-1 rounded transition-colors text-xs font-mono ${
                        formState.defaultExecutionMode === 'LIVE'
                          ? 'bg-warning-bg text-warning border border-warning font-bold'
                          : 'text-text-muted hover:text-text-strong'
                      }`}
                    >
                      LIVE GATEWAY
                    </button>
                  </div>
                </div>

                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Trading Window Schedule</div>
                  <div className="text-text-muted text-[11px]">Restrict autonomous trading to specific regional market sessions.</div>
                  <div className="grid grid-cols-3 gap-1 pt-1">
                    {[
                      { id: '24_7_GLOBAL', label: '24/7 Global' },
                      { id: 'MARKET_HOURS_NYSE', label: 'NYSE Core' },
                      { id: 'LONDON_NY_OVERLAP', label: 'LDN/NY Overlap' }
                    ].map((w) => (
                      <button
                        key={w.id}
                        onClick={() => handleChange('tradingWindowMode', w.id as any)}
                        className={`py-1 px-1 rounded text-[11px] font-mono transition-colors truncate border ${
                          formState.tradingWindowMode === w.id
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {w.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Multi-Sig & Anomaly De-escalation & Cooldown */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Multi-Signature Threshold</div>
                  <div className="text-text-muted text-[11px]">Orders exceeding this require 2-of-3 keys.</div>
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-text-muted">$</span>
                    <input
                      type="number"
                      value={formState.multiSigThresholdUsd}
                      onChange={(e) => handleChange('multiSigThresholdUsd', Number(e.target.value))}
                      className="bg-surface-deep border border-border-strong rounded px-3 py-1 text-xs text-text-strong font-mono w-full focus:border-accent focus:outline-none"
                    />
                  </div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Rebalance Cooldown</div>
                  <div className="text-text-muted text-[11px]">Minimum buffer between automated rebalances.</div>
                  <div className="flex items-center gap-2 pt-1">
                    <input
                      type="number"
                      value={formState.rebalanceCooldownMinutes}
                      onChange={(e) => handleChange('rebalanceCooldownMinutes', Number(e.target.value))}
                      className="bg-surface-deep border border-border-strong rounded px-3 py-1 text-xs text-text-strong font-mono w-full focus:border-accent focus:outline-none"
                    />
                    <span className="text-text-muted">min</span>
                  </div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="font-bold text-text-strong text-xs">Anomaly De-escalation</div>
                    <input
                      type="checkbox"
                      checked={formState.autoDeescalateOnAnomaly}
                      onChange={(e) => handleChange('autoDeescalateOnAnomaly', e.target.checked)}
                      className="w-4 h-4 rounded accent-accent cursor-pointer"
                    />
                  </div>
                  <div className="text-text-muted text-[11px]">Step down to MANUAL if covariance matrix detects &gt;3σ shock.</div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: Risk Limits & Firewall */}
          {activeSection === 'risk' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-warning" />
                    RISK LIMITS & CONSTITUTIONAL FIREWALL RULES
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Immutable guardrails enforced at kernel level before any order can enter the SOR execution pipeline.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-warning-bg text-warning border border-warning font-bold">
                  CONSTITUTION §2.1 ENFORCED
                </span>
              </div>

              {/* Drawdown Tier Sliders */}
              <div className="space-y-4 p-4 rounded bg-surface-veil border border-border-subtle">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Tiered Drawdown De-risking Escalation
                </div>

                {/* Tier 1: Warning */}
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-text flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-warning"></span>
                      Tier 1: Warning & Scrutiny Threshold
                    </span>
                    <span className="font-bold text-warning font-mono">{formState.warningDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="3.0"
                    step="0.05"
                    value={formState.warningDrawdownPct}
                    onChange={(e) => handleChange('warningDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-warning"
                  />
                  <div className="text-[10px] text-text-muted">Agents pause high-beta expansion; alert dispatched to risk desk.</div>
                </div>

                {/* Tier 2: De-risking */}
                <div className="space-y-1 pt-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-text flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-warning"></span>
                      Tier 2: Mandatory De-risking & Size Halving
                    </span>
                    <span className="font-bold text-warning font-mono">{formState.deriskDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="1.0"
                    max="4.0"
                    step="0.05"
                    value={formState.deriskDrawdownPct}
                    onChange={(e) => handleChange('deriskDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-warning"
                  />
                  <div className="text-[10px] text-text-muted">System cuts gross exposure by 50% and flattens top 2 high-beta positions.</div>
                </div>

                {/* Tier 3: Emergency Halt */}
                <div className="space-y-1 pt-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-text flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-destructive"></span>
                      Tier 3: Emergency Kill Switch & Liquidation Halt
                    </span>
                    <span className="font-bold text-destructive font-mono">{formState.emergencyHaltDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="2.0"
                    max="5.0"
                    step="0.05"
                    value={formState.emergencyHaltDrawdownPct}
                    onChange={(e) => handleChange('emergencyHaltDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-destructive"
                  />
                  <div className="text-[10px] text-text-muted">HARD CEILING (Constitution Rule #1): Cancels open orders and flattens to cash.</div>
                </div>
              </div>

              {/* Concentration Caps & Tail Risk Limits */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Max Single Asset Cap</span>
                    <span className="text-accent font-mono">{formState.maxPositionConcentrationPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="30"
                    step="1"
                    value={formState.maxPositionConcentrationPct}
                    onChange={(e) => handleChange('maxPositionConcentrationPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Max portfolio allocation in one symbol.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Max Asset Class Cap</span>
                    <span className="text-accent font-mono">{formState.maxClassExposurePct}%</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="60"
                    step="1"
                    value={formState.maxClassExposurePct}
                    onChange={(e) => handleChange('maxClassExposurePct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Max exposure to Equities or Crypto.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Expected Shortfall (CVaR)</span>
                    <span className="text-warning font-mono">{formState.expectedShortfallCapPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="2.0"
                    max="8.0"
                    step="0.25"
                    value={formState.expectedShortfallCapPct}
                    onChange={(e) => handleChange('expectedShortfallCapPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-warning"
                  />
                  <div className="text-[10px] text-text-muted">99.9% 1-day tail risk loss budget.</div>
                </div>
              </div>

              {/* Leverage & Overnight Protocols */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Cash-Only Discipline (1.0x Gross Leverage)</div>
                    <div className="text-text-muted text-[11px]">Strict cash-settled balance sheet. Never borrow margin or deploy debt.</div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-positive-bg text-positive border border-positive font-bold">
                    ENFORCED
                  </span>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Overnight De-risking Protocol</div>
                    <div className="text-text-muted text-[11px]">Reduce perpetual exposure by 20% prior to Asian session rollover.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.overnightDerisking}
                    onChange={(e) => handleChange('overnightDerisking', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 3: Multi-Agent Tuning & LLM Model Gatekeeper */}
          {activeSection === 'agents' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <BrainCircuit className="w-4 h-4 text-accent" />
                    MULTI-AGENT CONSENSUS, DEBATE GOVERNANCE & LLM ROUTING
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Configure LangGraph voting quorums, adversarial cross-examination, and per-agent foundation model backends.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
                  LANGGRAPH ORCHESTRATOR
                </span>
              </div>

              {/* Consensus Threshold & Debate Rounds */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Supermajority Consensus Quorum</span>
                    <span className="text-accent font-mono font-bold">{formState.minConsensusThresholdPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="60"
                    max="95"
                    step="1"
                    value={formState.minConsensusThresholdPct}
                    onChange={(e) => handleChange('minConsensusThresholdPct', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Proposals need ≥{formState.minConsensusThresholdPct}% agreement to pass the synthesis gate.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Maximum Adversarial Debate Rounds</div>
                  <div className="flex gap-2 pt-1">
                    {[1, 2, 3, 5].map((rounds) => (
                      <button
                        key={rounds}
                        onClick={() => handleChange('maxDebateRounds', rounds)}
                        className={`flex-1 py-1 rounded text-xs font-mono transition-colors border ${
                          formState.maxDebateRounds === rounds
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {rounds} {rounds === 1 ? 'Round' : 'Rounds'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Dedicated Model Routing */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider flex items-center justify-between">
                  <span>Dedicated LLM Model Routing per Agent Specialist</span>
                  <span className="text-[10px] text-accent">Multi-Model Ensemble</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div className="space-y-1 p-2.5 rounded bg-surface-sunken border border-border-subtle">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-text-strong">Macro Regime Specialist</span>
                      <span className="text-accent font-mono text-[10px]">High Context</span>
                    </div>
                    <select
                      value={formState.macroAgentModel}
                      onChange={(e) => handleChange('macroAgentModel', e.target.value)}
                      className="w-full bg-surface-deep border border-border-strong rounded px-2.5 py-1 text-xs text-text-strong font-mono focus:border-accent focus:outline-none"
                    >
                      <option value="Gemini 2.5 Pro (Thinking)">Gemini 2.5 Pro (Thinking &amp; Macro Ingestion)</option>
                      <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet (Synthesizer)</option>
                      <option value="GPT-4o Enterprise">GPT-4o Enterprise Direct</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-surface-sunken border border-border-subtle">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-text-strong">Quant Momentum Specialist</span>
                      <span className="text-positive font-mono text-[10px]">Fast Inference</span>
                    </div>
                    <select
                      value={formState.quantAgentModel}
                      onChange={(e) => handleChange('quantAgentModel', e.target.value)}
                      className="w-full bg-surface-deep border border-border-strong rounded px-2.5 py-1 text-xs text-text-strong font-mono focus:border-accent focus:outline-none"
                    >
                      <option value="DeepSeek R1 / Flash Hybrid">DeepSeek R1 / Flash Hybrid (Chain of Thought)</option>
                      <option value="Gemini 2.5 Flash">Gemini 2.5 Flash (Sub-100ms)</option>
                      <option value="Qwen 2.5 72B Quant">Qwen 2.5 72B Quant Specialized</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-surface-sunken border border-border-subtle">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-text-strong">Sentiment &amp; Flow Specialist</span>
                      <span className="text-accent font-mono text-[10px]">News Stream</span>
                    </div>
                    <select
                      value={formState.sentimentAgentModel}
                      onChange={(e) => handleChange('sentimentAgentModel', e.target.value)}
                      className="w-full bg-surface-deep border border-border-strong rounded px-2.5 py-1 text-xs text-text-strong font-mono focus:border-accent focus:outline-none"
                    >
                      <option value="Gemini 2.5 Flash">Gemini 2.5 Flash (Real-time Stream)</option>
                      <option value="Llama 3.3 70B Fast">Llama 3.3 70B Fast Tokenizer</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-surface-sunken border border-border-subtle">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-destructive">Risk Sentinel &amp; Adversary Gate</span>
                      <span className="text-destructive font-mono text-[10px]">Hard Veto</span>
                    </div>
                    <select
                      value={formState.riskSentinelModel}
                      onChange={(e) => handleChange('riskSentinelModel', e.target.value)}
                      className="w-full bg-surface-deep border border-border-strong rounded px-2.5 py-1 text-xs text-text-strong font-mono focus:border-accent focus:outline-none"
                    >
                      <option value="Deterministic Rust + Gemini 2.5 Pro">Deterministic Rust + Gemini 2.5 Pro Veto</option>
                      <option value="Formal Verification SMT + Python">Formal Verification SMT Solver</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Temperature & Prompt Injection Guard */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Inference Temperature</span>
                    <span className="text-accent font-mono font-bold">{formState.inferenceTemperature.toFixed(2)} (Deterministic)</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="0.7"
                    step="0.05"
                    value={formState.inferenceTemperature}
                    onChange={(e) => handleChange('inferenceTemperature', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Low temperature minimizes hallucination and ensures math consistency.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Prompt Injection Sanitizer &amp; Guardrail</div>
                    <div className="text-text-muted text-[11px]">Strips adversarial inputs from web scrape and social sentiment feeds.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.promptSanitizerActive}
                    onChange={(e) => handleChange('promptSanitizerActive', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: Execution & Venues */}
          {activeSection === 'execution' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Zap className="w-4 h-4 text-accent" />
                    SMART ORDER ROUTING (SOR) & VENUE GATEWAYS
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Configure institutional FIX protocols, latency thresholds, slicing engines, and dark pool routing.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-positive-bg text-positive border border-positive font-bold">
                  ALL 5 GATEWAYS ONLINE
                </span>
              </div>

              {/* Execution Algorithm & Slippage */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Default Algorithmic Slicer</div>
                  <div className="grid grid-cols-3 gap-1.5 pt-1">
                    {(['TWAP', 'VWAP', 'POV', 'ICEBERG', 'IMPLEMENTATION_SHORTFALL'] as const).map((algo) => (
                      <button
                        key={algo}
                        onClick={() => handleChange('defaultAlgorithm', algo)}
                        className={`py-1 px-1 rounded text-[11px] font-mono transition-colors truncate border ${
                          formState.defaultAlgorithm === algo
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {algo}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Max Allowed Slippage Tolerance</span>
                    <span className="text-positive font-mono font-bold">{formState.maxSlippageBps} BPS</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="10.0"
                    step="0.5"
                    value={formState.maxSlippageBps}
                    onChange={(e) => handleChange('maxSlippageBps', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-positive"
                  />
                  <div className="text-[10px] text-text-muted">Orders abort if market impact exceeds {formState.maxSlippageBps} basis points.</div>
                </div>
              </div>

              {/* Venue Table */}
              <div className="space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider flex items-center justify-between">
                  <span>Connected Institutional Venues &amp; Direct Gateway Feeds</span>
                  <span className="text-[10px] text-text-muted">Direct FIX &amp; REST/WS</span>
                </div>

                <div className="space-y-2">
                  {formState.venues.map((venue) => (
                    <div
                      key={venue.id}
                      className="p-3 rounded bg-surface-veil border border-border-subtle flex flex-wrap items-center justify-between gap-3 text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={venue.enabled}
                          onChange={(e) => handleVenueToggle(venue.id, e.target.checked)}
                          className="w-4 h-4 rounded accent-accent cursor-pointer"
                        />
                        <div>
                          <div className="flex items-center gap-2 font-bold text-text-strong">
                            <span>{venue.name}</span>
                            <span className="text-[9px] px-1 rounded bg-surface-sunken text-text-muted border border-border-strong font-mono">
                              {venue.gatewayType}
                            </span>
                            {venue.ipWhitelistVerified && (
                              <span className="text-[9px] text-positive flex items-center gap-0.5">
                                <Check className="w-2.5 h-2.5" /> IP Whitelisted
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-text-muted font-mono mt-0.5">
                            {venue.endpoint} • Key: {venue.apiKeyMasked}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="text-[10px] text-text-muted">LATENCY</div>
                          <div className="text-positive font-mono font-bold">{venue.latencyMs} ms</div>
                        </div>

                        <span
                          title="No venue probe endpoint exists — venue rows are persisted config, not live status"
                          className="px-2.5 py-1 rounded bg-surface-veil border border-border-subtle text-text-subtle text-[11px]"
                        >
                          NO PROBE
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* On-Chain Gas & MEV Flashbots */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Max Gas Priority Cap</span>
                    <span className="text-accent font-mono font-bold">{formState.gasMaxGweiCap} Gwei</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="200"
                    step="5"
                    value={formState.gasMaxGweiCap}
                    onChange={(e) => handleChange('gasMaxGweiCap', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Cap max gas price on on-chain DEX routes during congestion.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Flashbots MEV Protection (Private RPC)</div>
                    <div className="text-text-muted text-[11px]">Bypasses public mempools to eliminate sandwich attacks &amp; frontrunning.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.flashbotsMevProtection}
                    onChange={(e) => handleChange('flashbotsMevProtection', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION: TradingView API & Charting Library Integration */}
          {activeSection === 'tradingview' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-accent" />
                    TRADINGVIEW ADVANCED CHARTING LIBRARY & DATAFEED API
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Configure official TradingView Pro API credentials, custom datafeeds, webhook signal triggers, and default technical studies.
                  </p>
                </div>
                <span
                  title="No datafeed probe harness exists — credentials persist server-side only"
                  className="px-3 py-1.5 rounded bg-surface-veil border border-border-strong text-text-subtle text-xs font-bold"
                >
                  NO TEST HARNESS
                </span>
              </div>

              {/* Master Activation Toggle */}
              <div className="p-4 rounded-lg bg-violet border border-violet flex items-center justify-between">
                <div>
                  <div className="font-bold text-text-strong text-xs flex items-center gap-2">
                    <span>Enable TradingView Advanced Charting & API Gateway</span>
                    <span className="px-1.5 py-0.5 rounded bg-violet text-violet text-[9px] font-bold border border-violet">
                      INSTITUTIONAL LICENSE
                    </span>
                  </div>
                  <div className="text-text-muted text-[11px] mt-0.5">
                    Enables the official TradingView charting engine alongside low-latency native canvas feeds in the Live Trading space.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={formState.tradingViewApiEnabled}
                  onChange={(e) => handleChange('tradingViewApiEnabled', e.target.checked)}
                  className="w-5 h-5 rounded accent-accent cursor-pointer"
                />
              </div>

              {/* API Credentials & Datafeed URL */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                  <div className="font-bold text-text-strong text-xs uppercase tracking-wider flex items-center gap-2">
                    <Key className="w-3.5 h-3.5 text-accent" />
                    TradingView API Key (Bearer / Secret)
                  </div>
                  <input
                    type="password"
                    value={formState.tradingViewApiKey}
                    onChange={(e) => handleChange('tradingViewApiKey', e.target.value)}
                    placeholder="tv_live_pk_..."
                    className="w-full bg-surface-deep border border-border-subtle rounded px-3 py-2 text-text-strong font-mono text-xs outline-none focus:border-accent"
                  />
                  <div className="text-[10px] text-text-muted">
                    Used to authenticate high-frequency UDF/JS-API requests against TradingView Hosted Datafeeds.
                  </div>
                </div>

                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                  <div className="font-bold text-text-strong text-xs uppercase tracking-wider flex items-center gap-2">
                    <Radio className="w-3.5 h-3.5 text-violet" />
                    Datafeed Gateway Endpoint URL
                  </div>
                  <input
                    type="text"
                    value={formState.tradingViewDatafeedUrl}
                    onChange={(e) => handleChange('tradingViewDatafeedUrl', e.target.value)}
                    placeholder="https://datafeed.tradingview.com/v1"
                    className="w-full bg-surface-deep border border-border-subtle rounded px-3 py-2 text-text-strong font-mono text-xs outline-none focus:border-accent"
                  />
                  <div className="text-[10px] text-text-muted">
                    WebSocket and REST endpoint streaming historical OHLCV & real-time tick bars.
                  </div>
                </div>
              </div>

              {/* Chart Defaults & Preferences */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-4">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Default Charting Engine Configuration
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-text-muted text-[10px] uppercase font-bold block mb-1">Default Timeframe Interval</label>
                    <select
                      value={formState.tradingViewInterval}
                      onChange={(e) => handleChange('tradingViewInterval', e.target.value as any)}
                      className="w-full bg-surface-deep border border-border-subtle rounded px-2.5 py-1.5 text-text-strong text-xs outline-none focus:border-accent"
                    >
                      <option value="1">1 Minute (Ultra High Frequency)</option>
                      <option value="5">5 Minutes</option>
                      <option value="15">15 Minutes (Default)</option>
                      <option value="60">1 Hour</option>
                      <option value="240">4 Hours</option>
                      <option value="D">1 Day</option>
                      <option value="W">1 Week</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-text-muted text-[10px] uppercase font-bold block mb-1">Default Chart Style</label>
                    <select
                      value={formState.tradingViewChartType}
                      onChange={(e) => handleChange('tradingViewChartType', e.target.value as any)}
                      className="w-full bg-surface-deep border border-border-subtle rounded px-2.5 py-1.5 text-text-strong text-xs outline-none focus:border-accent"
                    >
                      <option value="CANDLES">Japanese Candlesticks</option>
                      <option value="HEIKIN_ASHI">Heikin Ashi Smoothed</option>
                      <option value="LINE">Line (Close-only)</option>
                      <option value="AREA">Area Gradient</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-text-muted text-[10px] uppercase font-bold block mb-1">Color Palette Theme</label>
                    <select
                      value={formState.tradingViewDefaultTheme}
                      onChange={(e) => handleChange('tradingViewDefaultTheme', e.target.value as any)}
                      className="w-full bg-surface-deep border border-border-subtle rounded px-2.5 py-1.5 text-text-strong text-xs outline-none focus:border-accent"
                    >
                      <option value="dark">Institutional Dark (Default)</option>
                      <option value="light">Daylight Light</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <label className="flex items-center gap-2 text-xs text-text cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.tradingViewShowVolume}
                      onChange={(e) => handleChange('tradingViewShowVolume', e.target.checked)}
                      className="w-4 h-4 rounded accent-accent"
                    />
                    <span>Render Real-time Volume Profile & Delta Histogram</span>
                  </label>

                  <label className="flex items-center gap-2 text-xs text-text cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.tradingViewShowIndicators}
                      onChange={(e) => handleChange('tradingViewShowIndicators', e.target.checked)}
                      className="w-4 h-4 rounded accent-accent"
                    />
                    <span>Auto-load Technical Indicator Presets on Symbol Switch</span>
                  </label>
                </div>
              </div>

              {/* TradingView Webhooks & Alert Signal Bridge */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-text-strong text-xs uppercase tracking-wider flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5 text-warning" />
                    TradingView Webhook Signal & Strategy Alert Bridge
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.tradingViewWebhooksEnabled}
                    onChange={(e) => handleChange('tradingViewWebhooksEnabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>

                <p className="text-text-muted text-xs">
                  Execute Pine Script strategies directly into the aios0x Risk Firewall via signed JSON Webhooks.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div>
                    <label className="text-text-muted text-[10px] uppercase font-bold block mb-1">Webhook Ingress URL</label>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        readOnly
                        value="https://api.aios0x.institution.internal/v1/webhooks/tradingview-signals"
                        className="flex-1 bg-surface-deep border border-border-subtle rounded px-2.5 py-1.5 text-text font-mono text-[10px]"
                      />
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText("https://api.aios0x.institution.internal/v1/webhooks/tradingview-signals");
                          onTriggerToast('Copied TradingView Webhook URL to clipboard.');
                        }}
                        className="px-2 py-1.5 rounded bg-surface-veil border border-border-subtle hover:bg-surface-raised text-text text-xs"
                        title="Copy Webhook URL"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="text-text-muted text-[10px] uppercase font-bold block mb-1">Webhook HMAC Secret Signature</label>
                    <input
                      type="password"
                      value={formState.tradingViewWebhookSecret}
                      onChange={(e) => handleChange('tradingViewWebhookSecret', e.target.value)}
                      className="w-full bg-surface-deep border border-border-subtle rounded px-2.5 py-1.5 text-text-strong font-mono text-xs outline-none focus:border-accent"
                    />
                  </div>
                </div>
              </div>

              {/* Active Indicator Presets */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Active Indicator Presets in Trading Workspace
                </div>
                <div className="flex flex-wrap gap-2">
                  {formState.tradingViewActiveIndicators.map((ind, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded bg-surface-sunken border border-accent text-accent text-xs flex items-center gap-1.5 font-mono"
                    >
                      <Check className="w-3 h-3 text-accent" />
                      {ind}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* SECTION 5: Data Feeds & Oracles */}
          {activeSection === 'oracles' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Radio className="w-4 h-4 text-accent" />
                    DECENTRALIZED ORACLES & HIGH-FREQUENCY MARKET DATA SLA
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Configure dual-oracle validation rules, price staleness limits, and cross-venue deviation circuit breakers.
                  </p>
                </div>
                <span
                  title="No oracle probe harness exists — thresholds persist server-side only"
                  className="px-3 py-1 rounded bg-surface-veil border border-border-strong text-text-subtle text-xs font-bold"
                >
                  NO TEST HARNESS
                </span>
              </div>

              {/* Oracle Providers */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Primary Oracle Architecture
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { id: 'CHAINLINK_PYTH_DUAL', name: 'Dual Chainlink + Pyth', desc: 'Recommended: Full cross-validation' },
                    { id: 'CHAINLINK_ONLY', name: 'Chainlink Only', desc: 'Decentralized quorum' },
                    { id: 'PYTH_ONLY', name: 'Pyth High-Frequency', desc: 'Sub-400ms low latency' },
                    { id: 'SWITCHBOARD', name: 'Switchboard Modular', desc: 'Custom feed aggregation' },
                  ].map((oracle) => (
                    <button
                      key={oracle.id}
                      onClick={() => handleChange('oracleProvider', oracle.id as any)}
                      className={`p-3 rounded border text-left transition-colors ${
                        formState.oracleProvider === oracle.id
                          ? 'bg-info-bg border-accent text-text-strong shadow-sm'
                          : 'bg-surface-sunken border-border-subtle text-text-muted hover:text-text-strong'
                      }`}
                    >
                      <div className="font-bold text-xs">{oracle.name}</div>
                      <div className="text-[10px] text-text-muted mt-1">{oracle.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Staleness and Deviation */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Oracle Staleness Circuit Breaker</span>
                    <span className="text-accent font-mono font-bold">{formState.oracleStalenessMaxSec} Seconds</span>
                  </div>
                  <input
                    type="range"
                    min="3"
                    max="30"
                    step="1"
                    value={formState.oracleStalenessMaxSec}
                    onChange={(e) => handleChange('oracleStalenessMaxSec', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Halts trading if price feed has not updated within {formState.oracleStalenessMaxSec}s.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Max Cross-Feed Deviation</span>
                    <span className="text-accent font-mono font-bold">{formState.maxOracleDeviationBps} BPS ({(formState.maxOracleDeviationBps / 100).toFixed(2)}%)</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="100"
                    step="5"
                    value={formState.maxOracleDeviationBps}
                    onChange={(e) => handleChange('maxOracleDeviationBps', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Triggers arbitration check if Chainlink and Pyth diverge by &gt; {formState.maxOracleDeviationBps} bps.</div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 6: Stress Testing & Monte Carlo */}
          {activeSection === 'backtest' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <LineChart className="w-4 h-4 text-accent" />
                    HISTORICAL STRESS TESTING &amp; MONTE CARLO SIMULATOR
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Subject current portfolio weights to extreme tail risk events and 100,000 synthetic market paths.
                  </p>
                </div>
                <span
                  title="No stress-test harness exists — scenario and budgets persist server-side only"
                  className="px-4 py-1.5 rounded bg-surface-veil border border-border-strong text-text-subtle text-xs font-bold"
                >
                  NO TEST HARNESS
                </span>
              </div>

              {/* Stress Preset Scenarios */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Select Stress Test Scenario
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { id: 'COVID_CRASH_2020', name: '2020 COVID Liquidity Shock', shock: '-34% Equities, -50% Crypto' },
                    { id: 'GFC_2008', name: '2008 Lehman Brothers Crash', shock: '-55% S&P 500, Yield Crash' },
                    { id: 'TERRA_FTX_2022', name: '2022 Terra/FTX Contagion', shock: '-70% Crypto, Depeg Shock' },
                    { id: 'RATE_HIKE_500BPS', name: '+500bps Sovereign Rate Hike', shock: 'Yield Curve Inversion' },
                  ].map((scen) => (
                    <button
                      key={scen.id}
                      onClick={() => handleChange('stressTestScenario', scen.id as any)}
                      className={`p-3 rounded border text-left transition-colors ${
                        formState.stressTestScenario === scen.id
                          ? 'bg-info-bg border-accent text-text-strong shadow-sm'
                          : 'bg-surface-sunken border-border-subtle text-text-muted hover:text-text-strong'
                      }`}
                    >
                      <div className="font-bold text-xs">{scen.name}</div>
                      <div className="text-[10px] text-warning font-mono mt-1">{scen.shock}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Simulation Runs & Lookback */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Monte Carlo Path Iterations</span>
                    <span className="text-accent font-mono font-bold">{formState.monteCarloSimulationsCount.toLocaleString()} Paths</span>
                  </div>
                  <input
                    type="range"
                    min="10000"
                    max="100000"
                    step="5000"
                    value={formState.monteCarloSimulationsCount}
                    onChange={(e) => handleChange('monteCarloSimulationsCount', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Historical Lookback Window</span>
                    <span className="text-accent font-mono font-bold">{formState.backtestLookbackYears} Years</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="1"
                    value={formState.backtestLookbackYears}
                    onChange={(e) => handleChange('backtestLookbackYears', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                </div>
              </div>

              {/* No stress engine exists server-side: scenario + budgets persist, nothing executes */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle text-xs text-text-muted leading-relaxed">
                No stress-test harness is wired. The scenario, path budget, and lookback above are stored
                with the server blob when you save — no simulation runs from this panel. Walk-forward
                backtests live under the Strategies tab (POST /api/v1/research/backtest).
              </div>
            </div>
          )}

          {/* SECTION 7: Accounting, Tax & Financial Controller */}
          {activeSection === 'accounting' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <ReceiptText className="w-4 h-4 text-accent" />
                    ACCOUNTING, TAX LOT OPTIMIZATION &amp; FUND CONTROLLER OVERSIGHT
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Tax harvesting rules, double-entry general ledger rules, and daily Compliance Controller sign-off policies.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
                  HIFO ACTIVE
                </span>
              </div>

              {/* Tax Lot Method */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Tax Lot Selection Algorithm
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {(['HIFO', 'FIFO', 'LIFO', 'SpecID'] as const).map((method) => (
                    <button
                      key={method}
                      onClick={() => handleChange('taxLotMethod', method)}
                      className={`p-2.5 rounded border text-left transition-colors ${
                        formState.taxLotMethod === method
                          ? 'bg-info-bg border-accent text-text-strong shadow-sm'
                          : 'bg-surface-sunken border-border-subtle text-text-muted hover:text-text-strong'
                      }`}
                    >
                      <div className="font-bold text-xs">{method}</div>
                      <div className="text-[10px] text-text-muted mt-0.5">
                        {method === 'HIFO' && 'Highest-In First-Out (Min Tax)'}
                        {method === 'FIFO' && 'First-In First-Out'}
                        {method === 'LIFO' && 'Last-In First-Out'}
                        {method === 'SpecID' && 'Specific Lot Identifier'}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Automated Tax-Loss Harvesting */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Automated Tax-Loss Harvesting</div>
                    <div className="text-text-muted text-[11px]">Harvest realized tax losses and rotate into non-wash proxy assets.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.autoTaxLossHarvesting}
                    onChange={(e) => handleChange('autoTaxLossHarvesting', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Tax-Loss Trigger Threshold</span>
                    <span className="text-accent font-mono font-bold">${formState.taxLossHarvestMinLossUsd.toLocaleString()}</span>
                  </div>
                  <input
                    type="range"
                    min="10000"
                    max="200000"
                    step="5000"
                    value={formState.taxLossHarvestMinLossUsd}
                    onChange={(e) => handleChange('taxLossHarvestMinLossUsd', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Trigger harvesting when position unrealized loss &gt; threshold.</div>
                </div>
              </div>

              {/* Capital Gains Provision & Functional Currency */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Automated Capital Gains Tax Provision Rate</span>
                    <span className="text-accent font-mono font-bold">{formState.capGainsProvisionRatePct}%</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="40"
                    step="0.5"
                    value={formState.capGainsProvisionRatePct}
                    onChange={(e) => handleChange('capGainsProvisionRatePct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Escrows {formState.capGainsProvisionRatePct}% of realized profits into liquidity reserve.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Base Functional Currency</div>
                  <div className="grid grid-cols-3 gap-1.5 pt-1">
                    {(['USD', 'EUR', 'GBP', 'CHF', 'SGD', 'JPY'] as const).map((curr) => (
                      <button
                        key={curr}
                        onClick={() => handleChange('baseReportingCurrency', curr)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.baseReportingCurrency === curr
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {curr}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Daily Controller Sign-Off & Wash Sale Guard */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Daily Controller &amp; Compliance Sign-Off</div>
                    <div className="text-text-muted text-[11px]">Require Fund Controller manual ratification before daily midnight ledger seal.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.dailyControllerSignOffRequired}
                    onChange={(e) => handleChange('dailyControllerSignOffRequired', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Wash Sale Guard (30-Day Rule)</div>
                    <div className="text-text-muted text-[11px]">Block automated re-entry into realized loss securities within 30 days.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.washSaleGuard}
                    onChange={(e) => handleChange('washSaleGuard', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 8: API Keys & Secrets Vault */}
          {activeSection === 'apikeys' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Key className="w-4 h-4 text-accent" />
                    API CREDENTIALS, SECRETS VAULT &amp; GATEWAYS
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Hardware-enclave encrypted exchange keys, AI inference tokens, and regulatory data feed credentials.
                  </p>
                </div>
              </div>

              {/* No secrets backend exists: never demonstrated fake credentials here */}
              <div className="p-6 rounded bg-surface-veil border border-border-subtle text-center">
                <div className="text-xs font-bold text-text-strong">NO SECRETS VAULT WIRED</div>
                <div className="text-[11px] text-text-muted mt-1 leading-relaxed">
                  No credential store exists server-side, so this panel holds no keys and accepts none.
                  Do not paste secrets into the settings blob — it is stored as plain JSON.
                </div>
              </div>
            </div>
          )}

          {/* SECTION 9: Alerts & Webhooks */}
          {activeSection === 'alerts' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Bell className="w-4 h-4 text-accent" />
                    REAL-TIME NOTIFICATIONS, PAGERDUTY &amp; TELEGRAM BOT
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Configure institutional alert channels for drawdown warnings, consensus deadlocks, and fill anomalies.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
                  ACTIVE WEBHOOK PIPELINE
                </span>
              </div>

              {/* Alert Toggles */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Critical Event Subscriptions
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  {[
                    { key: 'alertOnDrawdownWarning', label: 'Drawdown Warning (Tier 1 & 2)', desc: 'Immediate dispatch on drawdown threshold touch.' },
                    { key: 'alertOnDrawdownDerisk', label: 'Mandatory De-risking & Kill Switch', desc: 'PagerDuty critical alert with phone escalation.' },
                    { key: 'alertOnLargeFills', label: 'Large Execution Fills (> $500k)', desc: 'Summary of TWAP/VWAP completion and slippage.' },
                    { key: 'alertOnDebateDeadlock', label: 'Agent Debate Deadlocks (<60% Consensus)', desc: 'Alert when agents fail to reach quorum in 3 rounds.' },
                    { key: 'alertOnMerkleBlock', label: 'Merkle Audit Tree Tamper Detection', desc: 'Zero-tolerance alert on any block hash mismatch.' },
                  ].map((item) => (
                    <div key={item.key} className="flex items-center justify-between p-2.5 rounded bg-surface-sunken border border-border-subtle">
                      <div>
                        <div className="font-semibold text-text-strong text-xs">{item.label}</div>
                        <div className="text-[10px] text-text-muted">{item.desc}</div>
                      </div>
                      <input
                        type="checkbox"
                        checked={formState[item.key as keyof SystemSettings] as boolean}
                        onChange={(e) => handleChange(item.key as keyof SystemSettings, e.target.checked as any)}
                        className="w-4 h-4 rounded accent-accent cursor-pointer ml-3"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Webhook Endpoint */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Institutional Webhook URL (Slack / Teams / Custom Endpoint)
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={formState.webhookUrl}
                    onChange={(e) => handleChange('webhookUrl', e.target.value)}
                    className="bg-surface-deep border border-border-strong rounded px-3 py-1.5 text-xs text-text-strong font-mono flex-1 focus:border-accent focus:outline-none"
                  />
                  <span
                    title="No webhook dispatch harness exists — the URL persists server-side only"
                    className="px-3.5 py-1.5 rounded bg-surface-veil border border-border-strong text-text-subtle font-bold text-xs"
                  >
                    NO TEST HARNESS
                  </span>
                </div>
              </div>

              {/* Telegram Bot Alerts */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Telegram Instant Dispatch Channel</div>
                    <div className="text-text-muted text-[11px]">Direct priority messaging to executive incident management group.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.telegramAlertsEnabled}
                    onChange={(e) => handleChange('telegramAlertsEnabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
                {formState.telegramAlertsEnabled && (
                  <div className="flex gap-2 pt-1">
                    <input
                      type="text"
                      value={formState.telegramChatIdMasked}
                      onChange={(e) => handleChange('telegramChatIdMasked', e.target.value)}
                      placeholder="Telegram Group Chat ID (-100...)"
                      className="bg-surface-deep border border-border-strong rounded px-3 py-1 text-xs text-text-strong font-mono flex-1 focus:border-accent focus:outline-none"
                    />
                    <span
                      title="No Telegram dispatch harness exists — settings persist server-side only"
                      className="px-3 py-1 rounded bg-surface-veil border border-border-strong text-text-subtle text-xs font-bold"
                    >
                      NO TEST HARNESS
                    </span>
                  </div>
                )}
              </div>

              {/* Acoustic Alerts */}
              <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                <div>
                  <div className="font-bold text-text-strong text-xs">Institutional Acoustic Audio Alerts</div>
                  <div className="text-text-muted text-[11px]">Subtle low-frequency chimes for execution fills and risk events.</div>
                </div>
                <div className="flex items-center gap-2">
                  {(['SUBTLE', 'SONAR', 'MUTED'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => handleChange('acousticAlerts', mode)}
                      className={`px-3 py-1 rounded text-xs font-mono transition-colors border ${
                        formState.acousticAlerts === mode
                          ? 'bg-info-bg text-accent border-accent font-bold'
                          : 'bg-surface-sunken text-text-muted border-border-strong'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* SECTION 10: Display & UI Preferences */}
          {activeSection === 'display' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Monitor className="w-4 h-4 text-accent" />
                    DISPLAY PREFERENCES, TYPOGRAPHY &amp; PRIVACY
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Customize institutional data refresh frequencies, numerical monospace typography, and accent themes.
                  </p>
                </div>
                {/* The static "OLED DARK DEFAULT" badge that stood here asserted a
                    constant as though it were the current theme. It is replaced by the
                    live theme readout inside the Console Theme panel below. */}
              </div>

              <LayoutPanel tabs={WORKSPACE_TABS} activeTab={activeTab} onLayoutChange={onLayoutChange} />

              {/* Theme + Accent. Both apply immediately — see `chooseTheme` above for
                  why these are client-local rather than server settings. */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                    Console Theme
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
                    {THEME_LABELS.find(t => t.id === theme)?.name ?? theme}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {THEME_LABELS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      aria-pressed={theme === option.id}
                      onClick={() => chooseTheme(option.id)}
                      className={`p-3 rounded border text-left transition-all ${
                        theme === option.id
                          ? 'bg-surface-raised border-accent text-text-strong'
                          : 'bg-surface-sunken border-border-subtle text-text-muted hover:text-text-strong'
                      }`}
                    >
                      <span className="font-bold text-xs">{option.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Accent Theme Selector */}
              <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
                  Signature Intelligence Accent Palette
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {ACCENT_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      aria-pressed={accent === preset.id}
                      onClick={() => chooseAccent(preset.id)}
                      className={`p-3 rounded border text-left transition-all ${
                        accent === preset.id
                          ? 'bg-surface-raised border-accent text-text-strong shadow-md'
                          : 'bg-surface-sunken border-border-subtle text-text-muted hover:text-text-strong'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        {/* The swatch previews the preset by applying its own data-accent
                            locally, then reading the resolved token. A literal here would
                            show one colour while the console showed another, and would be
                            a hex outside index.css besides. */}
                        <span
                          className="w-3 h-3 rounded-full border border-border-subtle"
                          data-accent={preset.id}
                          style={{ backgroundColor: 'var(--color-accent)' }}
                        />
                        <span className="font-bold text-xs">{preset.name}</span>
                      </div>
                      <div className="text-[10px] text-text-muted">{preset.desc}</div>
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-text-subtle">
                  Accent applies to live, highlight and focus. Positive, warning and
                  destructive stay fixed, so &ldquo;nominal&rdquo; is never the same colour
                  as &ldquo;profitable&rdquo;.
                </p>
              </div>

              {/* Refresh Rate & Number Font */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Telemetry &amp; Trajectory Refresh Interval</div>
                  <div className="grid grid-cols-4 gap-1.5 pt-1">
                    {[500, 1000, 2000, 5000].map((ms) => (
                      <button
                        key={ms}
                        onClick={() => handleChange('refreshRateMs', ms)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.refreshRateMs === ms
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {ms}ms
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-text-muted">Controls polling rate of live orderbook feeds and trajectory charts.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Market Clock Timezone</div>
                  <div className="grid grid-cols-4 gap-1.5 pt-1">
                    {(['UTC', 'EST', 'GMT', 'JST'] as const).map((tz) => (
                      <button
                        key={tz}
                        onClick={() => handleChange('marketClockTimezone', tz)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.marketClockTimezone === tz
                            ? 'bg-info-bg text-accent border-accent font-bold'
                            : 'bg-surface-sunken text-text-muted border-border-strong'
                        }`}
                      >
                        {tz}
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-text-muted">Display header clock in institutional UTC or regional market session.</div>
                </div>
              </div>

              {/* High Density Mode & Balance Privacy Mask */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* REMOVED: `highDensityMode`. This toggle promised "tighter padding and
                    tabular numbers" and changed nothing — no consumer existed anywhere in
                    the tree, and it had done since before the token layer existed to
                    implement it. It is deleted rather than wired because no product
                    decision has been made about which density should ship by default, and
                    inventing one here would be presenting my guess as the platform's
                    design. See `numberFont` below for the same case. */}

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Privacy Balance Masking Mode</div>
                    <div className="text-text-muted text-[11px]">Masks portfolio NAV and order sizes ($***,***,***) for presentation security.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.privacyBalanceMask}
                    onChange={(e) => handleChange('privacyBalanceMask', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 11: Security & Multi-Sig */}
          {activeSection === 'security' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Lock className="w-4 h-4 text-accent" />
                    SECURITY, 2FA HARDWARE KEYS &amp; MULTI-SIG CUSTODY
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Hardware security module (HSM) keys, session timeouts, and role-based cryptographic permissions.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-positive-bg text-positive border border-positive font-bold">
                  HSM SECURE ENCLAVE
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="font-bold text-text-strong text-xs">2FA / FIDO2 Hardware Token Enforced</div>
                    <input
                      type="checkbox"
                      checked={formState.require2FAForRebalance}
                      onChange={(e) => handleChange('require2FAForRebalance', e.target.checked)}
                      className="w-4 h-4 rounded accent-accent cursor-pointer"
                    />
                  </div>
                  <div className="text-text-muted text-[11px]">Require YubiKey or WebAuthn physical tap when executing rebalances over $500k.</div>
                </div>

                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="font-bold text-text-strong text-xs">Master Operator Key Fingerprint</div>
                  <div className="p-2 rounded bg-surface-deep border border-border-strong font-mono text-[11px] text-text-subtle">
                    — (no HSM attestation published)
                  </div>
                  <div className="text-[10px] text-text-muted">Enclave Status: unknown — no attestation endpoint exists.</div>
                </div>
              </div>

              {/* Session Timeout and Kill Switch PIN */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-text-strong text-xs">Session Inactivity Lockout</span>
                    <span className="text-accent font-mono font-bold">{formState.sessionIdleTimeoutMinutes} Minutes</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="120"
                    step="5"
                    value={formState.sessionIdleTimeoutMinutes}
                    onChange={(e) => handleChange('sessionIdleTimeoutMinutes', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-surface-deep rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  <div className="text-[10px] text-text-muted">Auto-lock terminal workstation after idle time.</div>
                </div>

                <div className="p-3.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Emergency Kill Switch Safety PIN</div>
                    <div className="text-text-muted text-[11px]">Require 6-digit confirmation code before triggering full portfolio flatten.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.killSwitchRequirePin}
                    onChange={(e) => handleChange('killSwitchRequirePin', e.target.checked)}
                    className="w-4 h-4 rounded accent-accent cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 12: Backup & Export */}
          {activeSection === 'backup' && (
            <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-border-subtle pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider flex items-center gap-2">
                    <Download className="w-4 h-4 text-accent" />
                    SYSTEM BACKUP, MERKLE LEDGER EXPORT &amp; HARD RESET
                  </h3>
                  <p className="text-text-muted text-xs mt-0.5">
                    Export entire system configuration, upload JSON configurations, or restore default Constitution v1.0.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Export Config */}
                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Export Active Config (JSON)</div>
                    <div className="text-text-muted text-[11px] mt-1">
                      Download all current risk thresholds, agent model routes, venue credentials, and tax rules.
                    </div>
                  </div>
                  <button
                    onClick={handleExportConfig}
                    className="w-full py-2 rounded bg-info-bg hover:bg-info-bg border border-accent text-accent font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>EXPORT SYSTEM JSON</span>
                  </button>
                </div>

                {/* Import Config */}
                <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-text-strong text-xs">Import Configuration (JSON)</div>
                    <div className="text-text-muted text-[11px] mt-1">
                      Restore parameters from a previous configuration snapshot file.
                    </div>
                  </div>
                  <label className="w-full py-2 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-text-strong font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2 cursor-pointer">
                    <Upload className="w-4 h-4" />
                    <span>UPLOAD JSON FILE</span>
                    <input
                      type="file"
                      accept=".json"
                      onChange={handleImportConfigFile}
                      className="hidden"
                    />
                  </label>
                </div>

                {/* Reset Defaults */}
                <div className="p-4 rounded bg-surface-veil border border-destructive space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-destructive text-xs">Reset to Institutional Defaults</div>
                    <div className="text-text-muted text-[11px] mt-1">
                      Reverts all risk thresholds, agent quorum weights, and algorithms to the baseline Ratified Constitution v1.0.
                    </div>
                  </div>
                  <button
                    onClick={() => setShowResetConfirm(true)}
                    className="w-full py-2 rounded bg-destructive-bg hover:bg-destructive-bg border border-destructive text-destructive font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2"
                  >
                    <RotateCcw className="w-4 h-4" />
                    <span>RESET TO DEFAULT CONFIG</span>
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
      {/* Reset Confirmation Modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 z-50 bg-surface-sunken backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-[var(--color-surface-1)] border border-destructive rounded-lg p-5 shadow-2xl space-y-4 font-mono">
            <div className="flex items-center gap-2 text-destructive font-bold text-sm">
              <AlertTriangle className="w-5 h-5" />
              <span>CONFIRM SYSTEM CONFIG RESET</span>
            </div>
            <p className="text-text text-xs leading-relaxed">
              Are you sure you want to reset all operational limits, multi-agent weights, and venue configurations to institutional defaults? This action will overwrite any pending unsaved changes.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowResetConfirm(false)}
                className="px-3 py-1.5 rounded bg-surface-raised hover:bg-surface-overlay text-xs text-text"
              >
                CANCEL
              </button>
              <button
                onClick={() => {
                  onResetDefaults();
                  setShowResetConfirm(false);
                }}
                className="px-4 py-1.5 rounded bg-destructive hover:bg-destructive text-text-strong font-bold text-xs"
              >
                CONFIRM RESET
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
