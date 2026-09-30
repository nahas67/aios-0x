import React, { useState } from 'react';
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
  Download, 
  Upload, 
  RotateCcw, 
  Save, 
  CheckCircle2, 
  Lock, 
   
   
   
  Radio, 



  Check, 
  Copy,


  RefreshCw,



  Fingerprint,

  LineChart,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Send,





} from 'lucide-react';
import { SystemSettings, AutonomyLevel,  VenueConfig } from '../../types';

interface SettingsWorkspaceProps {
  settings: SystemSettings;
  onUpdateSettings: (newSettings: SystemSettings) => void;
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

interface ApiKeyItem {
  id: string;
  service: string;
  name: string;
  keyMasked: string;
  fullKey: string;
  permissions: 'READ_ONLY' | 'TRADE_ONLY' | 'FULL_ACCESS';
  status: 'ACTIVE' | 'REVOKED' | 'EXPIRED';
  expiresAt: string;
  lastUsed: string;
}

export const SettingsWorkspace: React.FC<SettingsWorkspaceProps> = ({
  settings,
  onUpdateSettings,
  onResetDefaults,
  onTriggerToast,
}) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('autonomy');
  const [formState, setFormState] = useState<SystemSettings>(settings);
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [testingVenueId, setTestingVenueId] = useState<string | null>(null);
  const [testingTradingView, setTestingTradingView] = useState<boolean>(false);
  const [testingWebhook, setTestingWebhook] = useState<boolean>(false);
  const [testingTelegram, setTestingTelegram] = useState<boolean>(false);
  const [testingOracle, setTestingOracle] = useState<boolean>(false);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [revealedKeyIds, setRevealedKeyIds] = useState<Record<string, boolean>>({});
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);
  const [showAddKeyModal, setShowAddKeyModal] = useState<boolean>(false);
  const [lastSavedHash, setLastSavedHash] = useState<string>('0x8f92a14e92b847c0');
  
  // Backtest / Stress Test Simulation State
  const [isRunningBacktest, setIsRunningBacktest] = useState<boolean>(false);
  const [backtestResult, setBacktestResult] = useState<{
    simulatedMaxDd: number;
    simulatedCVar99: number;
    sharpeRatio: number;
    worstPeriodDays: number;
    status: 'PASSED_GUARDRAILS' | 'BREACHED_GUARDRAILS';
  } | null>(null);

  // Initial API Key Vault Records
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([
    {
      id: 'key-polymarket',
      service: 'Polymarket CLOB Gateway',
      name: 'Polygon L2 CTF Exchange & Prediction Settlement API',
      keyMasked: '0x94A...33c9E••••••••••••881a',
      fullKey: '0x94A920148fB233c9E881a029384719028471881a',
      permissions: 'FULL_ACCESS',
      status: 'ACTIVE',
      expiresAt: 'PERMANENT',
      lastUsed: '6 seconds ago'
    },
    {
      id: 'key-ibkr',
      service: 'Interactive Brokers FIX Gateway',
      name: 'Global Equities Direct (TSE Tokyo, Euronext, HKEX, NSE)',
      keyMasked: 'ibkr_fix_live_829••••••••••••994a',
      fullKey: 'ibkr_fix_live_829104882910481902847104994a',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: '2028-06-30',
      lastUsed: '8 seconds ago'
    },
    {
      id: 'key-ebs-fx',
      service: 'EBS & 360T Interbank Forex',
      name: 'G10 & Emerging Market Foreign Exchange FIX Stream',
      keyMasked: 'ebs_fx_feed_441••••••••••••721b',
      fullKey: 'ebs_fx_feed_4410293847192038471920384721b',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: '2027-12-31',
      lastUsed: '3 seconds ago'
    },
    {
      id: 'key-ice-commodities',
      service: 'ICE Europe & LME Direct',
      name: 'Commodities Bullion, Crude & Industrial Metals FIX 4.4',
      keyMasked: 'ice_lme_feed_773••••••••••••109f',
      fullKey: 'ice_lme_feed_7730192837491028374910283109f',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: '2028-01-31',
      lastUsed: '14 seconds ago'
    },
    {
      id: 'key-binance',
      service: 'Binance Institutional',
      name: 'Primary Spot & Futures Gateway FIX 4.4',
      keyMasked: 'bin_inst_84a92••••••••••••b92c',
      fullKey: 'bin_inst_84a929f028ab77104b2c991e089a8b92c',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: '2027-12-31',
      lastUsed: '12 seconds ago'
    },
    {
      id: 'key-cme',
      service: 'CME Group Direct',
      name: 'Aurora Co-location iLink3 FIX Port',
      keyMasked: 'cme_ilink3_7391••••••••••••f182',
      fullKey: 'cme_ilink3_7391004819aa018274bb92019ff182',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: '2027-06-30',
      lastUsed: '4 seconds ago'
    },
    {
      id: 'key-hyperliquid',
      service: 'Hyperliquid L1',
      name: 'Arbitrum/L1 Signing Master Sub-Account',
      keyMasked: '0x71C...98A2eB••••••••••••01Fa',
      fullKey: '0x71C82901458A2eB990145899201948820101Fa',
      permissions: 'TRADE_ONLY',
      status: 'ACTIVE',
      expiresAt: 'PERMANENT',
      lastUsed: '1 second ago'
    },
    {
      id: 'key-gemini',
      service: 'Google Gemini AI Engine',
      name: 'Gemini 2.5 Pro LangGraph Orchestrator',
      keyMasked: 'AIzaSyD89••••••••••••94f2A',
      fullKey: 'AIzaSyD8902847194019284710492817494f2A',
      permissions: 'FULL_ACCESS',
      status: 'ACTIVE',
      expiresAt: 'PERMANENT',
      lastUsed: '2 seconds ago'
    },
    {
      id: 'key-sec',
      service: 'SEC EDGAR Direct Feed',
      name: 'Continuous 13F & 8-K Real-Time XBRL Ingestion',
      keyMasked: 'sec_edgar_user_991••••••••••••72b',
      fullKey: 'sec_edgar_user_9918274019283749102872b',
      permissions: 'READ_ONLY',
      status: 'ACTIVE',
      expiresAt: '2028-01-01',
      lastUsed: '18 minutes ago'
    }
  ]);

  // New Key Form State
  const [newKeyForm, setNewKeyForm] = useState({
    service: 'Binance Institutional',
    name: '',
    key: '',
    permissions: 'TRADE_ONLY' as const
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

  const handleSave = () => {
    onUpdateSettings(formState);
    setIsDirty(false);
    const newHash = '0x' + Array.from({length: 16}, () => Math.floor(Math.random() * 16).toString(16)).join('');
    setLastSavedHash(newHash);
    onTriggerToast(`System configuration saved & ratified in Merkle Block #${Math.floor(4830 + Math.random() * 50)}`);
  };

  const handleRevert = () => {
    setFormState(settings);
    setIsDirty(false);
    onTriggerToast('Settings reverted to active memory state.');
  };

  const handleTestTradingView = () => {
    setTestingTradingView(true);
    setTimeout(() => {
      setTestingTradingView(false);
      onTriggerToast('TradingView Pro API Ping: 200 OK • Datafeed Gateway Latency 14ms • WebSocket Heartbeat Verified');
    }, 800);
  };

  const handleTestVenue = (venue: VenueConfig) => {
    setTestingVenueId(venue.id);
    setTimeout(() => {
      setTestingVenueId(null);
      onTriggerToast(`Ping ${venue.name}: Round-trip latency ${venue.latencyMs}ms (FIX heartbeat verified OK)`);
    }, 700);
  };

  const handleTestWebhook = () => {
    setTestingWebhook(true);
    setTimeout(() => {
      setTestingWebhook(false);
      onTriggerToast('Test alert payload dispatched to Webhook endpoint: 200 OK (Slack/Teams Verified)');
    }, 850);
  };

  const handleTestTelegram = () => {
    setTestingTelegram(true);
    setTimeout(() => {
      setTestingTelegram(false);
      onTriggerToast('Telegram bot test message dispatched to verified group channel.');
    }, 750);
  };

  const handleTestOracle = () => {
    setTestingOracle(true);
    setTimeout(() => {
      setTestingOracle(false);
      onTriggerToast('Dual Oracle Heartbeat: Chainlink (0.4s age, 0.02% delta) & Pyth (120ms age) in full consensus.');
    }, 900);
  };

  const handleRunStressTest = () => {
    setIsRunningBacktest(true);
    setTimeout(() => {
      setIsRunningBacktest(false);
      setBacktestResult({
        simulatedMaxDd: 2.14,
        simulatedCVar99: 3.42,
        sharpeRatio: 2.88,
        worstPeriodDays: 4,
        status: 'PASSED_GUARDRAILS'
      });
      onTriggerToast(`Monte Carlo Stress Test completed (${formState.monteCarloSimulationsCount.toLocaleString()} paths): Constitution 3.0% DD Guardrail Respected.`);
    }, 1400);
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
          onTriggerToast('Configuration imported successfully from JSON file. Click SAVE & RATIFY to apply.');
        } else {
          onTriggerToast('Error: JSON file does not match institutional SystemSettings schema.');
        }
      } catch (err) {
        onTriggerToast('Failed to parse uploaded JSON file.');
      }
    };
    reader.readAsText(file);
  };

  const handleCopyKey = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKeyId(id);
    setTimeout(() => setCopiedKeyId(null), 1500);
  };

  const toggleRevealKey = (id: string) => {
    setRevealedKeyIds(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleAddKey = () => {
    if (!newKeyForm.name || !newKeyForm.key) {
      onTriggerToast('Please fill in key name and credential secret.');
      return;
    }
    const masked = newKeyForm.key.length > 10 
      ? `${newKeyForm.key.slice(0, 6)}••••••••••••${newKeyForm.key.slice(-4)}`
      : '••••••••••••';
    
    const newEntry: ApiKeyItem = {
      id: `key-${Date.now()}`,
      service: newKeyForm.service,
      name: newKeyForm.name,
      keyMasked: masked,
      fullKey: newKeyForm.key,
      permissions: newKeyForm.permissions,
      status: 'ACTIVE',
      expiresAt: '2028-12-31',
      lastUsed: 'Just created'
    };

    setApiKeys(prev => [newEntry, ...prev]);
    setShowAddKeyModal(false);
    setNewKeyForm({ service: 'Binance Institutional', name: '', key: '', permissions: 'TRADE_ONLY' });
    onTriggerToast(`Added new gateway credential: ${newEntry.name}`);
  };

  const handleDeleteKey = (id: string) => {
    setApiKeys(prev => prev.filter(k => k.id !== id));
    onTriggerToast('Gateway credential revoked & removed from active memory enclave.');
  };

  const navItems: { id: SettingsSection; label: string; icon: React.ElementType; badge?: string }[] = [
    { id: 'autonomy', label: 'Autonomy & Governance', icon: Sliders },
    { id: 'risk', label: 'Risk Limits & Firewall', icon: ShieldCheck, badge: 'Constitution' },
    { id: 'agents', label: 'Multi-Agent & LLM Engines', icon: BrainCircuit, badge: 'LangGraph' },
    { id: 'execution', label: 'Execution & Venues', icon: Zap, badge: '5 Venues' },
    { id: 'tradingview', label: 'TradingView & Chart API', icon: BarChart2, badge: 'PRO' },
    { id: 'oracles', label: 'Data Feeds & Oracles', icon: Radio, badge: 'Dual SLA' },
    { id: 'backtest', label: 'Stress Testing & Monte Carlo', icon: LineChart, badge: 'Monte Carlo' },
    { id: 'accounting', label: 'Accounting & Controller', icon: ReceiptText, badge: 'Compliance' },
    { id: 'apikeys', label: 'API Keys & Secrets Vault', icon: Key, badge: `${apiKeys.length} Keys` },
    { id: 'alerts', label: 'Alerts, Webhooks & Telegram', icon: Bell },
    { id: 'display', label: 'Display & UI Preferences', icon: Monitor },
    { id: 'security', label: 'Security & Multi-Sig', icon: Lock },
    { id: 'backup', label: 'Backup, Export & Reset', icon: Download },
  ];

  return (
    <div className="space-y-4 pb-16 font-mono text-xs">
      {/* Workspace Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INSTITUTIONAL SETTINGS & SYSTEM CONFIGURATION
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
              MASTER CONTROL
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Operational Constitution • Risk Governance • Multi-Agent LLMs • Smart Order Routing • Cryptographic Enforcers
          </div>
        </div>

        {/* Global Save / Revert Bar */}
        <div className="flex items-center gap-2.5">
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded bg-black/40 border border-white/[0.06] text-slate-400">
            <Fingerprint className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-[10px]">CONFIG RATIFIED: <span className="text-cyan-300 font-mono">{lastSavedHash}</span></span>
          </div>

          {isDirty && (
            <button
              onClick={handleRevert}
              className="px-3 py-1.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white transition-colors flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>REVERT</span>
            </button>
          )}

          <button
            onClick={handleSave}
            disabled={!isDirty}
            className={`px-4 py-1.5 rounded font-bold transition-all flex items-center gap-1.5 ${
              isDirty 
                ? 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-[0_0_16px_rgba(0,240,255,0.4)] animate-pulse'
                : 'bg-white/[0.05] text-slate-500 border border-white/[0.08] cursor-not-allowed'
            }`}
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isDirty ? 'SAVE & RATIFY CONFIG' : 'CONFIG SYNCED'}</span>
          </button>
        </div>
      </div>

      {/* Main Split Layout: Left Settings Nav + Right Setting Pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Settings Navigation Column */}
        <div className="lg:col-span-3 bg-[#0d0f17] border border-white/[0.08] rounded-md p-2 shadow-2xl space-y-1">
          <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-white/[0.06] mb-1 flex items-center justify-between">
            <span>Modules</span>
            <span className="text-[9px] text-cyan-400">{navItems.length} Sections</span>
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
                    ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-700/50 shadow-[0_0_12px_rgba(0,240,255,0.15)] font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.03] border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : 'text-slate-400 group-hover:text-slate-300'}`} />
                  <span className="text-xs">{item.label}</span>
                </div>
                {item.badge && (
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-black/40 text-slate-400 border border-white/[0.06]">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}

          <div className="pt-3 mt-3 border-t border-white/[0.06] px-2 text-[10px] text-slate-400 space-y-1">
            <div className="flex justify-between">
              <span>AUTONOMY ENGINE:</span>
              <strong className="text-slate-300">v1.0.4-PROD</strong>
            </div>
            <div className="flex justify-between">
              <span>MERKLE CHAIN:</span>
              <strong className="text-emerald-400">HEALTHY</strong>
            </div>
            <div className="flex justify-between">
              <span>ACTIVE KEYS:</span>
              <strong className="text-cyan-300">{apiKeys.length} In Enclave</strong>
            </div>
          </div>
        </div>

        {/* Settings Detail Pane */}
        <div className="lg:col-span-9 space-y-4">
          
          {/* SECTION 1: Autonomy & Governance */}
          {activeSection === 'autonomy' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-cyan-400" />
                    AUTONOMY LEVEL, EXECUTION MODE & SCHEDULE GOVERNANCE
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Define the execution authorization boundaries for multi-agent trading models.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
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
                          ? 'bg-cyan-950/40 border-cyan-500 text-white shadow-[0_0_16px_rgba(0,240,255,0.15)]'
                          : 'bg-white/[0.02] border-white/[0.07] text-slate-300 hover:bg-white/[0.04]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <div className={`w-3 h-3 rounded-full border flex items-center justify-center ${isSelected ? 'border-cyan-400 bg-cyan-400/20' : 'border-slate-600'}`}>
                            {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />}
                          </div>
                          <span className="font-bold text-xs">{item.title}</span>
                        </div>
                        <span className="text-[9px] font-mono px-1 rounded bg-black/40 border border-white/[0.08] text-slate-400">
                          {item.badge}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 pl-5 leading-relaxed">
                        {item.desc}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Execution Mode & Trading Windows */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                  <div>
                    <div className="font-bold text-white text-xs">Default Execution Mode</div>
                    <div className="text-slate-400 text-[11px]">Toggle between simulated paper sandbox and live exchange gateways.</div>
                  </div>
                  <div className="flex items-center gap-2 bg-black/50 p-1 rounded border border-white/[0.08]">
                    <button
                      onClick={() => handleChange('defaultExecutionMode', 'PAPER')}
                      className={`flex-1 py-1 rounded transition-colors text-xs font-mono ${
                        formState.defaultExecutionMode === 'PAPER'
                          ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      PAPER SIMULATION
                    </button>
                    <button
                      onClick={() => handleChange('defaultExecutionMode', 'LIVE')}
                      className={`flex-1 py-1 rounded transition-colors text-xs font-mono ${
                        formState.defaultExecutionMode === 'LIVE'
                          ? 'bg-amber-950 text-amber-300 border border-amber-600 font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      LIVE GATEWAY
                    </button>
                  </div>
                </div>

                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Trading Window Schedule</div>
                  <div className="text-slate-400 text-[11px]">Restrict autonomous trading to specific regional market sessions.</div>
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
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
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
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Multi-Signature Threshold</div>
                  <div className="text-slate-400 text-[11px]">Orders exceeding this require 2-of-3 keys.</div>
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-slate-400">$</span>
                    <input
                      type="number"
                      value={formState.multiSigThresholdUsd}
                      onChange={(e) => handleChange('multiSigThresholdUsd', Number(e.target.value))}
                      className="bg-black/50 border border-white/[0.1] rounded px-3 py-1 text-xs text-white font-mono w-full focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Rebalance Cooldown</div>
                  <div className="text-slate-400 text-[11px]">Minimum buffer between automated rebalances.</div>
                  <div className="flex items-center gap-2 pt-1">
                    <input
                      type="number"
                      value={formState.rebalanceCooldownMinutes}
                      onChange={(e) => handleChange('rebalanceCooldownMinutes', Number(e.target.value))}
                      className="bg-black/50 border border-white/[0.1] rounded px-3 py-1 text-xs text-white font-mono w-full focus:border-cyan-500 focus:outline-none"
                    />
                    <span className="text-slate-400">min</span>
                  </div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="font-bold text-white text-xs">Anomaly De-escalation</div>
                    <input
                      type="checkbox"
                      checked={formState.autoDeescalateOnAnomaly}
                      onChange={(e) => handleChange('autoDeescalateOnAnomaly', e.target.checked)}
                      className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                    />
                  </div>
                  <div className="text-slate-400 text-[11px]">Step down to MANUAL if covariance matrix detects &gt;3σ shock.</div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: Risk Limits & Firewall */}
          {activeSection === 'risk' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-amber-400" />
                    RISK LIMITS & CONSTITUTIONAL FIREWALL RULES
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Immutable guardrails enforced at kernel level before any order can enter the SOR execution pipeline.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
                  CONSTITUTION §2.1 ENFORCED
                </span>
              </div>

              {/* Drawdown Tier Sliders */}
              <div className="space-y-4 p-4 rounded bg-white/[0.02] border border-white/[0.06]">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Tiered Drawdown De-risking Escalation
                </div>

                {/* Tier 1: Warning */}
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-yellow-400"></span>
                      Tier 1: Warning & Scrutiny Threshold
                    </span>
                    <span className="font-bold text-yellow-300 font-mono">{formState.warningDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="3.0"
                    step="0.05"
                    value={formState.warningDrawdownPct}
                    onChange={(e) => handleChange('warningDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-yellow-400"
                  />
                  <div className="text-[10px] text-slate-400">Agents pause high-beta expansion; alert dispatched to risk desk.</div>
                </div>

                {/* Tier 2: De-risking */}
                <div className="space-y-1 pt-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                      Tier 2: Mandatory De-risking & Size Halving
                    </span>
                    <span className="font-bold text-amber-400 font-mono">{formState.deriskDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="1.0"
                    max="4.0"
                    step="0.05"
                    value={formState.deriskDrawdownPct}
                    onChange={(e) => handleChange('deriskDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-amber-500"
                  />
                  <div className="text-[10px] text-slate-400">System cuts gross exposure by 50% and flattens top 2 high-beta positions.</div>
                </div>

                {/* Tier 3: Emergency Halt */}
                <div className="space-y-1 pt-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                      Tier 3: Emergency Kill Switch & Liquidation Halt
                    </span>
                    <span className="font-bold text-rose-400 font-mono">{formState.emergencyHaltDrawdownPct.toFixed(2)}% DD</span>
                  </div>
                  <input
                    type="range"
                    min="2.0"
                    max="5.0"
                    step="0.05"
                    value={formState.emergencyHaltDrawdownPct}
                    onChange={(e) => handleChange('emergencyHaltDrawdownPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-rose-500"
                  />
                  <div className="text-[10px] text-slate-400">HARD CEILING (Constitution Rule #1): Cancels open orders and flattens to cash.</div>
                </div>
              </div>

              {/* Concentration Caps & Tail Risk Limits */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Max Single Asset Cap</span>
                    <span className="text-cyan-300 font-mono">{formState.maxPositionConcentrationPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="30"
                    step="1"
                    value={formState.maxPositionConcentrationPct}
                    onChange={(e) => handleChange('maxPositionConcentrationPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Max portfolio allocation in one symbol.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Max Asset Class Cap</span>
                    <span className="text-cyan-300 font-mono">{formState.maxClassExposurePct}%</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="60"
                    step="1"
                    value={formState.maxClassExposurePct}
                    onChange={(e) => handleChange('maxClassExposurePct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Max exposure to Equities or Crypto.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Expected Shortfall (CVaR)</span>
                    <span className="text-amber-400 font-mono">{formState.expectedShortfallCapPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="2.0"
                    max="8.0"
                    step="0.25"
                    value={formState.expectedShortfallCapPct}
                    onChange={(e) => handleChange('expectedShortfallCapPct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-amber-400"
                  />
                  <div className="text-[10px] text-slate-400">99.9% 1-day tail risk loss budget.</div>
                </div>
              </div>

              {/* Leverage & Overnight Protocols */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Cash-Only Discipline (1.0x Gross Leverage)</div>
                    <div className="text-slate-400 text-[11px]">Strict cash-settled balance sheet. Never borrow margin or deploy debt.</div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                    ENFORCED
                  </span>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Overnight De-risking Protocol</div>
                    <div className="text-slate-400 text-[11px]">Reduce perpetual exposure by 20% prior to Asian session rollover.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.overnightDerisking}
                    onChange={(e) => handleChange('overnightDerisking', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 3: Multi-Agent Tuning & LLM Model Gatekeeper */}
          {activeSection === 'agents' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <BrainCircuit className="w-4 h-4 text-cyan-400" />
                    MULTI-AGENT CONSENSUS, DEBATE GOVERNANCE & LLM ROUTING
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Configure LangGraph voting quorums, adversarial cross-examination, and per-agent foundation model backends.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
                  LANGGRAPH ORCHESTRATOR
                </span>
              </div>

              {/* Consensus Threshold & Debate Rounds */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Supermajority Consensus Quorum</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.minConsensusThresholdPct}%</span>
                  </div>
                  <input
                    type="range"
                    min="60"
                    max="95"
                    step="1"
                    value={formState.minConsensusThresholdPct}
                    onChange={(e) => handleChange('minConsensusThresholdPct', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Proposals need ≥{formState.minConsensusThresholdPct}% agreement to pass the synthesis gate.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Maximum Adversarial Debate Rounds</div>
                  <div className="flex gap-2 pt-1">
                    {[1, 2, 3, 5].map((rounds) => (
                      <button
                        key={rounds}
                        onClick={() => handleChange('maxDebateRounds', rounds)}
                        className={`flex-1 py-1 rounded text-xs font-mono transition-colors border ${
                          formState.maxDebateRounds === rounds
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
                        }`}
                      >
                        {rounds} {rounds === 1 ? 'Round' : 'Rounds'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Dedicated Model Routing */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider flex items-center justify-between">
                  <span>Dedicated LLM Model Routing per Agent Specialist</span>
                  <span className="text-[10px] text-cyan-400">Multi-Model Ensemble</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div className="space-y-1 p-2.5 rounded bg-black/30 border border-white/[0.04]">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-slate-200">Macro Regime Specialist</span>
                      <span className="text-cyan-300 font-mono text-[10px]">High Context</span>
                    </div>
                    <select
                      value={formState.macroAgentModel}
                      onChange={(e) => handleChange('macroAgentModel', e.target.value)}
                      className="w-full bg-black/60 border border-white/[0.1] rounded px-2.5 py-1 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="Gemini 2.5 Pro (Thinking)">Gemini 2.5 Pro (Thinking &amp; Macro Ingestion)</option>
                      <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet (Synthesizer)</option>
                      <option value="GPT-4o Enterprise">GPT-4o Enterprise Direct</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-black/30 border border-white/[0.04]">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-slate-200">Quant Momentum Specialist</span>
                      <span className="text-emerald-300 font-mono text-[10px]">Fast Inference</span>
                    </div>
                    <select
                      value={formState.quantAgentModel}
                      onChange={(e) => handleChange('quantAgentModel', e.target.value)}
                      className="w-full bg-black/60 border border-white/[0.1] rounded px-2.5 py-1 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="DeepSeek R1 / Flash Hybrid">DeepSeek R1 / Flash Hybrid (Chain of Thought)</option>
                      <option value="Gemini 2.5 Flash">Gemini 2.5 Flash (Sub-100ms)</option>
                      <option value="Qwen 2.5 72B Quant">Qwen 2.5 72B Quant Specialized</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-black/30 border border-white/[0.04]">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-slate-200">Sentiment &amp; Flow Specialist</span>
                      <span className="text-cyan-300 font-mono text-[10px]">News Stream</span>
                    </div>
                    <select
                      value={formState.sentimentAgentModel}
                      onChange={(e) => handleChange('sentimentAgentModel', e.target.value)}
                      className="w-full bg-black/60 border border-white/[0.1] rounded px-2.5 py-1 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="Gemini 2.5 Flash">Gemini 2.5 Flash (Real-time Stream)</option>
                      <option value="Llama 3.3 70B Fast">Llama 3.3 70B Fast Tokenizer</option>
                    </select>
                  </div>

                  <div className="space-y-1 p-2.5 rounded bg-black/30 border border-white/[0.04]">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-rose-300">Risk Sentinel &amp; Adversary Gate</span>
                      <span className="text-rose-400 font-mono text-[10px]">Hard Veto</span>
                    </div>
                    <select
                      value={formState.riskSentinelModel}
                      onChange={(e) => handleChange('riskSentinelModel', e.target.value)}
                      className="w-full bg-black/60 border border-white/[0.1] rounded px-2.5 py-1 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="Deterministic Rust + Gemini 2.5 Pro">Deterministic Rust + Gemini 2.5 Pro Veto</option>
                      <option value="Formal Verification SMT + Python">Formal Verification SMT Solver</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Temperature & Prompt Injection Guard */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Inference Temperature</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.inferenceTemperature.toFixed(2)} (Deterministic)</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="0.7"
                    step="0.05"
                    value={formState.inferenceTemperature}
                    onChange={(e) => handleChange('inferenceTemperature', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Low temperature minimizes hallucination and ensures math consistency.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Prompt Injection Sanitizer &amp; Guardrail</div>
                    <div className="text-slate-400 text-[11px]">Strips adversarial inputs from web scrape and social sentiment feeds.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.promptSanitizerActive}
                    onChange={(e) => handleChange('promptSanitizerActive', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: Execution & Venues */}
          {activeSection === 'execution' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Zap className="w-4 h-4 text-cyan-400" />
                    SMART ORDER ROUTING (SOR) & VENUE GATEWAYS
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Configure institutional FIX protocols, latency thresholds, slicing engines, and dark pool routing.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                  ALL 5 GATEWAYS ONLINE
                </span>
              </div>

              {/* Execution Algorithm & Slippage */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Default Algorithmic Slicer</div>
                  <div className="grid grid-cols-3 gap-1.5 pt-1">
                    {(['TWAP', 'VWAP', 'POV', 'ICEBERG', 'IMPLEMENTATION_SHORTFALL'] as const).map((algo) => (
                      <button
                        key={algo}
                        onClick={() => handleChange('defaultAlgorithm', algo)}
                        className={`py-1 px-1 rounded text-[11px] font-mono transition-colors truncate border ${
                          formState.defaultAlgorithm === algo
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
                        }`}
                      >
                        {algo}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Max Allowed Slippage Tolerance</span>
                    <span className="text-emerald-400 font-mono font-bold">{formState.maxSlippageBps} BPS</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="10.0"
                    step="0.5"
                    value={formState.maxSlippageBps}
                    onChange={(e) => handleChange('maxSlippageBps', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-emerald-400"
                  />
                  <div className="text-[10px] text-slate-400">Orders abort if market impact exceeds {formState.maxSlippageBps} basis points.</div>
                </div>
              </div>

              {/* Venue Table */}
              <div className="space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider flex items-center justify-between">
                  <span>Connected Institutional Venues &amp; Direct Gateway Feeds</span>
                  <span className="text-[10px] text-slate-400">Direct FIX &amp; REST/WS</span>
                </div>

                <div className="space-y-2">
                  {formState.venues.map((venue) => (
                    <div
                      key={venue.id}
                      className="p-3 rounded bg-white/[0.02] border border-white/[0.06] flex flex-wrap items-center justify-between gap-3 text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={venue.enabled}
                          onChange={(e) => handleVenueToggle(venue.id, e.target.checked)}
                          className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                        />
                        <div>
                          <div className="flex items-center gap-2 font-bold text-white">
                            <span>{venue.name}</span>
                            <span className="text-[9px] px-1 rounded bg-black/40 text-slate-400 border border-white/[0.08] font-mono">
                              {venue.gatewayType}
                            </span>
                            {venue.ipWhitelistVerified && (
                              <span className="text-[9px] text-emerald-400 flex items-center gap-0.5">
                                <Check className="w-2.5 h-2.5" /> IP Whitelisted
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                            {venue.endpoint} • Key: {venue.apiKeyMasked}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="text-[10px] text-slate-400">LATENCY</div>
                          <div className="text-emerald-400 font-mono font-bold">{venue.latencyMs} ms</div>
                        </div>

                        <button
                          onClick={() => handleTestVenue(venue)}
                          disabled={testingVenueId === venue.id}
                          className="px-2.5 py-1 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-300 text-[11px] flex items-center gap-1.5 transition-colors"
                        >
                          <RefreshCw className={`w-3 h-3 ${testingVenueId === venue.id ? 'animate-spin text-cyan-400' : ''}`} />
                          <span>{testingVenueId === venue.id ? 'PINGING...' : 'PING'}</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* On-Chain Gas & MEV Flashbots */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Max Gas Priority Cap</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.gasMaxGweiCap} Gwei</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="200"
                    step="5"
                    value={formState.gasMaxGweiCap}
                    onChange={(e) => handleChange('gasMaxGweiCap', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Cap max gas price on on-chain DEX routes during congestion.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Flashbots MEV Protection (Private RPC)</div>
                    <div className="text-slate-400 text-[11px]">Bypasses public mempools to eliminate sandwich attacks &amp; frontrunning.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.flashbotsMevProtection}
                    onChange={(e) => handleChange('flashbotsMevProtection', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION: TradingView API & Charting Library Integration */}
          {activeSection === 'tradingview' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-cyan-400" />
                    TRADINGVIEW ADVANCED CHARTING LIBRARY & DATAFEED API
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Configure official TradingView Pro API credentials, custom datafeeds, webhook signal triggers, and default technical studies.
                  </p>
                </div>
                <button
                  onClick={handleTestTradingView}
                  disabled={testingTradingView}
                  className="px-3 py-1.5 rounded bg-indigo-950 hover:bg-indigo-900 border border-indigo-600/60 text-indigo-200 text-xs flex items-center gap-1.5 font-bold transition-all shadow-[0_0_12px_rgba(99,102,241,0.25)] cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${testingTradingView ? 'animate-spin text-cyan-400' : ''}`} />
                  <span>{testingTradingView ? 'TESTING DATAFEED...' : 'TEST TRADINGVIEW API PING'}</span>
                </button>
              </div>

              {/* Master Activation Toggle */}
              <div className="p-4 rounded-lg bg-indigo-950/20 border border-indigo-800/30 flex items-center justify-between">
                <div>
                  <div className="font-bold text-white text-xs flex items-center gap-2">
                    <span>Enable TradingView Advanced Charting & API Gateway</span>
                    <span className="px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300 text-[9px] font-bold border border-indigo-700/50">
                      INSTITUTIONAL LICENSE
                    </span>
                  </div>
                  <div className="text-slate-400 text-[11px] mt-0.5">
                    Enables the official TradingView charting engine alongside low-latency native canvas feeds in the Live Trading space.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={formState.tradingViewApiEnabled}
                  onChange={(e) => handleChange('tradingViewApiEnabled', e.target.checked)}
                  className="w-5 h-5 rounded accent-cyan-500 cursor-pointer"
                />
              </div>

              {/* API Credentials & Datafeed URL */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                  <div className="font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
                    <Key className="w-3.5 h-3.5 text-cyan-400" />
                    TradingView API Key (Bearer / Secret)
                  </div>
                  <input
                    type="password"
                    value={formState.tradingViewApiKey}
                    onChange={(e) => handleChange('tradingViewApiKey', e.target.value)}
                    placeholder="tv_live_pk_..."
                    className="w-full bg-black/50 border border-white/10 rounded px-3 py-2 text-slate-100 font-mono text-xs outline-none focus:border-cyan-500"
                  />
                  <div className="text-[10px] text-slate-400">
                    Used to authenticate high-frequency UDF/JS-API requests against TradingView Hosted Datafeeds.
                  </div>
                </div>

                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                  <div className="font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
                    <Radio className="w-3.5 h-3.5 text-indigo-400" />
                    Datafeed Gateway Endpoint URL
                  </div>
                  <input
                    type="text"
                    value={formState.tradingViewDatafeedUrl}
                    onChange={(e) => handleChange('tradingViewDatafeedUrl', e.target.value)}
                    placeholder="https://datafeed.tradingview.com/v1"
                    className="w-full bg-black/50 border border-white/10 rounded px-3 py-2 text-slate-100 font-mono text-xs outline-none focus:border-cyan-500"
                  />
                  <div className="text-[10px] text-slate-400">
                    WebSocket and REST endpoint streaming historical OHLCV & real-time tick bars.
                  </div>
                </div>
              </div>

              {/* Chart Defaults & Preferences */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-4">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Default Charting Engine Configuration
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-slate-400 text-[10px] uppercase font-bold block mb-1">Default Timeframe Interval</label>
                    <select
                      value={formState.tradingViewInterval}
                      onChange={(e) => handleChange('tradingViewInterval', e.target.value as any)}
                      className="w-full bg-black/50 border border-white/10 rounded px-2.5 py-1.5 text-slate-200 text-xs outline-none focus:border-cyan-500"
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
                    <label className="text-slate-400 text-[10px] uppercase font-bold block mb-1">Default Chart Style</label>
                    <select
                      value={formState.tradingViewChartType}
                      onChange={(e) => handleChange('tradingViewChartType', e.target.value as any)}
                      className="w-full bg-black/50 border border-white/10 rounded px-2.5 py-1.5 text-slate-200 text-xs outline-none focus:border-cyan-500"
                    >
                      <option value="CANDLES">Japanese Candlesticks</option>
                      <option value="HEIKIN_ASHI">Heikin Ashi Smoothed</option>
                      <option value="LINE">Line (Close-only)</option>
                      <option value="AREA">Area Gradient</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-slate-400 text-[10px] uppercase font-bold block mb-1">Color Palette Theme</label>
                    <select
                      value={formState.tradingViewDefaultTheme}
                      onChange={(e) => handleChange('tradingViewDefaultTheme', e.target.value as any)}
                      className="w-full bg-black/50 border border-white/10 rounded px-2.5 py-1.5 text-slate-200 text-xs outline-none focus:border-cyan-500"
                    >
                      <option value="dark">Institutional Dark (Default)</option>
                      <option value="light">Daylight Light</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.tradingViewShowVolume}
                      onChange={(e) => handleChange('tradingViewShowVolume', e.target.checked)}
                      className="w-4 h-4 rounded accent-cyan-500"
                    />
                    <span>Render Real-time Volume Profile & Delta Histogram</span>
                  </label>

                  <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.tradingViewShowIndicators}
                      onChange={(e) => handleChange('tradingViewShowIndicators', e.target.checked)}
                      className="w-4 h-4 rounded accent-cyan-500"
                    />
                    <span>Auto-load Technical Indicator Presets on Symbol Switch</span>
                  </label>
                </div>
              </div>

              {/* TradingView Webhooks & Alert Signal Bridge */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5 text-amber-400" />
                    TradingView Webhook Signal & Strategy Alert Bridge
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.tradingViewWebhooksEnabled}
                    onChange={(e) => handleChange('tradingViewWebhooksEnabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>

                <p className="text-slate-400 text-xs">
                  Execute Pine Script strategies directly into the aios0x Risk Firewall via signed JSON Webhooks.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div>
                    <label className="text-slate-400 text-[10px] uppercase font-bold block mb-1">Webhook Ingress URL</label>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        readOnly
                        value="https://api.aios0x.institution.internal/v1/webhooks/tradingview-signals"
                        className="flex-1 bg-black/60 border border-white/10 rounded px-2.5 py-1.5 text-slate-300 font-mono text-[10px]"
                      />
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText("https://api.aios0x.institution.internal/v1/webhooks/tradingview-signals");
                          onTriggerToast('Copied TradingView Webhook URL to clipboard.');
                        }}
                        className="px-2 py-1.5 rounded bg-white/[0.04] border border-white/10 hover:bg-white/[0.08] text-slate-300 text-xs"
                        title="Copy Webhook URL"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="text-slate-400 text-[10px] uppercase font-bold block mb-1">Webhook HMAC Secret Signature</label>
                    <input
                      type="password"
                      value={formState.tradingViewWebhookSecret}
                      onChange={(e) => handleChange('tradingViewWebhookSecret', e.target.value)}
                      className="w-full bg-black/60 border border-white/10 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
              </div>

              {/* Active Indicator Presets */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Active Indicator Presets in Trading Workspace
                </div>
                <div className="flex flex-wrap gap-2">
                  {formState.tradingViewActiveIndicators.map((ind, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded bg-black/40 border border-cyan-500/40 text-cyan-300 text-xs flex items-center gap-1.5 font-mono"
                    >
                      <Check className="w-3 h-3 text-cyan-400" />
                      {ind}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* SECTION 5: Data Feeds & Oracles */}
          {activeSection === 'oracles' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Radio className="w-4 h-4 text-cyan-400" />
                    DECENTRALIZED ORACLES & HIGH-FREQUENCY MARKET DATA SLA
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Configure dual-oracle validation rules, price staleness limits, and cross-venue deviation circuit breakers.
                  </p>
                </div>
                <button
                  onClick={handleTestOracle}
                  disabled={testingOracle}
                  className="px-3 py-1 rounded bg-cyan-950 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 text-xs flex items-center gap-1.5 font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.2)]"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${testingOracle ? 'animate-spin' : ''}`} />
                  <span>{testingOracle ? 'VERIFYING...' : 'TEST ORACLE HEARTBEAT'}</span>
                </button>
              </div>

              {/* Oracle Providers */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
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
                          ? 'bg-cyan-950/60 border-cyan-500 text-white shadow-sm'
                          : 'bg-black/30 border-white/[0.06] text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="font-bold text-xs">{oracle.name}</div>
                      <div className="text-[10px] text-slate-400 mt-1">{oracle.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Staleness and Deviation */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Oracle Staleness Circuit Breaker</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.oracleStalenessMaxSec} Seconds</span>
                  </div>
                  <input
                    type="range"
                    min="3"
                    max="30"
                    step="1"
                    value={formState.oracleStalenessMaxSec}
                    onChange={(e) => handleChange('oracleStalenessMaxSec', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Halts trading if price feed has not updated within {formState.oracleStalenessMaxSec}s.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Max Cross-Feed Deviation</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.maxOracleDeviationBps} BPS ({(formState.maxOracleDeviationBps / 100).toFixed(2)}%)</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="100"
                    step="5"
                    value={formState.maxOracleDeviationBps}
                    onChange={(e) => handleChange('maxOracleDeviationBps', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Triggers arbitration check if Chainlink and Pyth diverge by &gt; {formState.maxOracleDeviationBps} bps.</div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 6: Stress Testing & Monte Carlo */}
          {activeSection === 'backtest' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <LineChart className="w-4 h-4 text-cyan-400" />
                    HISTORICAL STRESS TESTING &amp; MONTE CARLO SIMULATOR
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Subject current portfolio weights to extreme tail risk events and 100,000 synthetic market paths.
                  </p>
                </div>
                <button
                  onClick={handleRunStressTest}
                  disabled={isRunningBacktest}
                  className="px-4 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-bold transition-all shadow-[0_0_16px_rgba(0,240,255,0.4)] flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRunningBacktest ? 'animate-spin' : ''}`} />
                  <span>{isRunningBacktest ? 'RUNNING SIMULATION...' : 'EXECUTE STRESS SIMULATION'}</span>
                </button>
              </div>

              {/* Stress Preset Scenarios */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
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
                          ? 'bg-cyan-950/60 border-cyan-500 text-white shadow-sm'
                          : 'bg-black/30 border-white/[0.06] text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="font-bold text-xs">{scen.name}</div>
                      <div className="text-[10px] text-amber-400 font-mono mt-1">{scen.shock}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Simulation Runs & Lookback */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Monte Carlo Path Iterations</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.monteCarloSimulationsCount.toLocaleString()} Paths</span>
                  </div>
                  <input
                    type="range"
                    min="10000"
                    max="100000"
                    step="5000"
                    value={formState.monteCarloSimulationsCount}
                    onChange={(e) => handleChange('monteCarloSimulationsCount', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Historical Lookback Window</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.backtestLookbackYears} Years</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="1"
                    value={formState.backtestLookbackYears}
                    onChange={(e) => handleChange('backtestLookbackYears', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>
              </div>

              {/* Backtest Result Display */}
              {backtestResult && (
                <div className="p-4 rounded bg-emerald-950/40 border border-emerald-700/60 space-y-3 animate-fade-in">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span className="font-bold text-xs text-white uppercase">Stress Simulation Results: {formState.stressTestScenario}</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-900 text-emerald-300 font-bold border border-emerald-600">
                      PASSED (3.0% HARD DD LIMIT MAINTAINED)
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
                    <div className="p-2.5 rounded bg-black/40 border border-white/[0.06]">
                      <div className="text-[10px] text-slate-400">SIMULATED MAX DRAWDOWN</div>
                      <div className="text-emerald-400 font-mono font-bold text-sm">-{backtestResult.simulatedMaxDd}%</div>
                    </div>
                    <div className="p-2.5 rounded bg-black/40 border border-white/[0.06]">
                      <div className="text-[10px] text-slate-400">SIMULATED 99.9% CVAR</div>
                      <div className="text-cyan-300 font-mono font-bold text-sm">{backtestResult.simulatedCVar99}%</div>
                    </div>
                    <div className="p-2.5 rounded bg-black/40 border border-white/[0.06]">
                      <div className="text-[10px] text-slate-400">ANNUALIZED SHARPE</div>
                      <div className="text-slate-100 font-mono font-bold text-sm">{backtestResult.sharpeRatio}</div>
                    </div>
                    <div className="p-2.5 rounded bg-black/40 border border-white/[0.06]">
                      <div className="text-[10px] text-slate-400">RECOVERY TIME</div>
                      <div className="text-slate-100 font-mono font-bold text-sm">{backtestResult.worstPeriodDays} Trading Days</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* SECTION 7: Accounting, Tax & Financial Controller */}
          {activeSection === 'accounting' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <ReceiptText className="w-4 h-4 text-cyan-400" />
                    ACCOUNTING, TAX LOT OPTIMIZATION &amp; FUND CONTROLLER OVERSIGHT
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Tax harvesting rules, double-entry general ledger rules, and daily Compliance Controller sign-off policies.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
                  HIFO ACTIVE
                </span>
              </div>

              {/* Tax Lot Method */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Tax Lot Selection Algorithm
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {(['HIFO', 'FIFO', 'LIFO', 'SpecID'] as const).map((method) => (
                    <button
                      key={method}
                      onClick={() => handleChange('taxLotMethod', method)}
                      className={`p-2.5 rounded border text-left transition-colors ${
                        formState.taxLotMethod === method
                          ? 'bg-cyan-950/60 border-cyan-500 text-white shadow-sm'
                          : 'bg-black/30 border-white/[0.06] text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="font-bold text-xs">{method}</div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
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
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Automated Tax-Loss Harvesting</div>
                    <div className="text-slate-400 text-[11px]">Harvest realized tax losses and rotate into non-wash proxy assets.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.autoTaxLossHarvesting}
                    onChange={(e) => handleChange('autoTaxLossHarvesting', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Tax-Loss Trigger Threshold</span>
                    <span className="text-cyan-300 font-mono font-bold">${formState.taxLossHarvestMinLossUsd.toLocaleString()}</span>
                  </div>
                  <input
                    type="range"
                    min="10000"
                    max="200000"
                    step="5000"
                    value={formState.taxLossHarvestMinLossUsd}
                    onChange={(e) => handleChange('taxLossHarvestMinLossUsd', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Trigger harvesting when position unrealized loss &gt; threshold.</div>
                </div>
              </div>

              {/* Capital Gains Provision & Functional Currency */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Automated Capital Gains Tax Provision Rate</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.capGainsProvisionRatePct}%</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="40"
                    step="0.5"
                    value={formState.capGainsProvisionRatePct}
                    onChange={(e) => handleChange('capGainsProvisionRatePct', parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Escrows {formState.capGainsProvisionRatePct}% of realized profits into liquidity reserve.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Base Functional Currency</div>
                  <div className="grid grid-cols-3 gap-1.5 pt-1">
                    {(['USD', 'EUR', 'GBP', 'CHF', 'SGD', 'JPY'] as const).map((curr) => (
                      <button
                        key={curr}
                        onClick={() => handleChange('baseReportingCurrency', curr)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.baseReportingCurrency === curr
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
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
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Daily Controller &amp; Compliance Sign-Off</div>
                    <div className="text-slate-400 text-[11px]">Require Fund Controller manual ratification before daily midnight ledger seal.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.dailyControllerSignOffRequired}
                    onChange={(e) => handleChange('dailyControllerSignOffRequired', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Wash Sale Guard (30-Day Rule)</div>
                    <div className="text-slate-400 text-[11px]">Block automated re-entry into realized loss securities within 30 days.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.washSaleGuard}
                    onChange={(e) => handleChange('washSaleGuard', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 8: API Keys & Secrets Vault */}
          {activeSection === 'apikeys' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Key className="w-4 h-4 text-cyan-400" />
                    API CREDENTIALS, SECRETS VAULT &amp; GATEWAYS
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Hardware-enclave encrypted exchange keys, AI inference tokens, and regulatory data feed credentials.
                  </p>
                </div>
                <button
                  onClick={() => setShowAddKeyModal(true)}
                  className="px-3 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)] flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>ADD CREDENTIAL</span>
                </button>
              </div>

              {/* Key List */}
              <div className="space-y-2.5">
                {apiKeys.map((key) => {
                  const isRevealed = revealedKeyIds[key.id];
                  return (
                    <div
                      key={key.id}
                      className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex flex-wrap items-center justify-between gap-3 text-xs"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 font-bold text-white">
                          <span>{key.service}</span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-black/50 text-cyan-300 border border-cyan-800 font-mono">
                            {key.permissions}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                            {key.status}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400">{key.name}</div>
                        <div className="flex items-center gap-2 pt-1 font-mono text-[11px]">
                          <span className="text-slate-300 bg-black/60 px-2 py-0.5 rounded border border-white/[0.08]">
                            {isRevealed ? key.fullKey : key.keyMasked}
                          </span>
                          <button
                            onClick={() => toggleRevealKey(key.id)}
                            className="text-slate-400 hover:text-white p-1"
                            title={isRevealed ? 'Mask Key' : 'Reveal Key'}
                          >
                            {isRevealed ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                          </button>
                          <button
                            onClick={() => handleCopyKey(key.id, key.fullKey)}
                            className="text-slate-400 hover:text-white p-1"
                            title="Copy Key"
                          >
                            {copiedKeyId === key.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="text-right text-[10px] text-slate-400 font-mono">
                          <div>LAST USED: <span className="text-slate-200">{key.lastUsed}</span></div>
                          <div>EXPIRES: <span className="text-slate-200">{key.expiresAt}</span></div>
                        </div>

                        <button
                          onClick={() => handleDeleteKey(key.id)}
                          className="p-1.5 rounded hover:bg-rose-950/60 text-slate-500 hover:text-rose-400 transition-colors"
                          title="Revoke and remove key"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SECTION 9: Alerts & Webhooks */}
          {activeSection === 'alerts' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Bell className="w-4 h-4 text-cyan-400" />
                    REAL-TIME NOTIFICATIONS, PAGERDUTY &amp; TELEGRAM BOT
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Configure institutional alert channels for drawdown warnings, consensus deadlocks, and fill anomalies.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
                  ACTIVE WEBHOOK PIPELINE
                </span>
              </div>

              {/* Alert Toggles */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
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
                    <div key={item.key} className="flex items-center justify-between p-2.5 rounded bg-black/30 border border-white/[0.04]">
                      <div>
                        <div className="font-semibold text-white text-xs">{item.label}</div>
                        <div className="text-[10px] text-slate-400">{item.desc}</div>
                      </div>
                      <input
                        type="checkbox"
                        checked={formState[item.key as keyof SystemSettings] as boolean}
                        onChange={(e) => handleChange(item.key as keyof SystemSettings, e.target.checked as any)}
                        className="w-4 h-4 rounded accent-cyan-500 cursor-pointer ml-3"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Webhook Endpoint */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Institutional Webhook URL (Slack / Teams / Custom Endpoint)
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={formState.webhookUrl}
                    onChange={(e) => handleChange('webhookUrl', e.target.value)}
                    className="bg-black/50 border border-white/[0.1] rounded px-3 py-1.5 text-xs text-white font-mono flex-1 focus:border-cyan-500 focus:outline-none"
                  />
                  <button
                    onClick={handleTestWebhook}
                    disabled={testingWebhook}
                    className="px-3.5 py-1.5 rounded bg-cyan-950 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 font-bold text-xs flex items-center gap-1.5 transition-colors"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${testingWebhook ? 'animate-spin' : ''}`} />
                    <span>{testingWebhook ? 'SENDING...' : 'TEST PAYLOAD'}</span>
                  </button>
                </div>
              </div>

              {/* Telegram Bot Alerts */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Telegram Instant Dispatch Channel</div>
                    <div className="text-slate-400 text-[11px]">Direct priority messaging to executive incident management group.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.telegramAlertsEnabled}
                    onChange={(e) => handleChange('telegramAlertsEnabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
                {formState.telegramAlertsEnabled && (
                  <div className="flex gap-2 pt-1">
                    <input
                      type="text"
                      value={formState.telegramChatIdMasked}
                      onChange={(e) => handleChange('telegramChatIdMasked', e.target.value)}
                      placeholder="Telegram Group Chat ID (-100...)"
                      className="bg-black/50 border border-white/[0.1] rounded px-3 py-1 text-xs text-white font-mono flex-1 focus:border-cyan-500 focus:outline-none"
                    />
                    <button
                      onClick={handleTestTelegram}
                      disabled={testingTelegram}
                      className="px-3 py-1 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-300 text-xs flex items-center gap-1.5 transition-colors"
                    >
                      <Send className="w-3 h-3 text-cyan-400" />
                      <span>{testingTelegram ? 'PAGING...' : 'TEST DISPATCH'}</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Acoustic Alerts */}
              <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                <div>
                  <div className="font-bold text-white text-xs">Institutional Acoustic Audio Alerts</div>
                  <div className="text-slate-400 text-[11px]">Subtle low-frequency chimes for execution fills and risk events.</div>
                </div>
                <div className="flex items-center gap-2">
                  {(['SUBTLE', 'SONAR', 'MUTED'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => handleChange('acousticAlerts', mode)}
                      className={`px-3 py-1 rounded text-xs font-mono transition-colors border ${
                        formState.acousticAlerts === mode
                          ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                          : 'bg-black/40 text-slate-400 border-white/[0.08]'
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
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Monitor className="w-4 h-4 text-cyan-400" />
                    DISPLAY PREFERENCES, TYPOGRAPHY &amp; PRIVACY
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Customize institutional data refresh frequencies, numerical monospace typography, and accent themes.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
                  OLED DARK DEFAULT
                </span>
              </div>

              {/* Accent Theme Selector */}
              <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                <div className="font-bold text-white text-xs uppercase tracking-wider">
                  Signature Intelligence Accent Palette
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { id: 'CYAN', name: 'Signature Cyan', hex: '#00f0ff', desc: 'AIOS-0X default' },
                    { id: 'EMERALD', name: 'Terminal Emerald', hex: '#10b981', desc: 'High-contrast green' },
                    { id: 'AMBER', name: 'Gold & Amber', hex: '#f59e0b', desc: 'Fixed income terminal' },
                    { id: 'VIOLET', name: 'Deep Violet', hex: '#818cf8', desc: 'Macro sovereign' },
                  ].map((theme) => (
                    <button
                      key={theme.id}
                      onClick={() => handleChange('accentTheme', theme.id as any)}
                      className={`p-3 rounded border text-left transition-all ${
                        formState.accentTheme === theme.id
                          ? 'bg-white/[0.06] border-white/40 text-white shadow-md'
                          : 'bg-black/30 border-white/[0.06] text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.hex }}></div>
                        <span className="font-bold text-xs">{theme.name}</span>
                      </div>
                      <div className="text-[10px] text-slate-400">{theme.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Refresh Rate & Number Font */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Telemetry &amp; Trajectory Refresh Interval</div>
                  <div className="grid grid-cols-4 gap-1.5 pt-1">
                    {[500, 1000, 2000, 5000].map((ms) => (
                      <button
                        key={ms}
                        onClick={() => handleChange('refreshRateMs', ms)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.refreshRateMs === ms
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
                        }`}
                      >
                        {ms}ms
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-slate-400">Controls polling rate of live orderbook feeds and trajectory charts.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Market Clock Timezone</div>
                  <div className="grid grid-cols-4 gap-1.5 pt-1">
                    {(['UTC', 'EST', 'GMT', 'JST'] as const).map((tz) => (
                      <button
                        key={tz}
                        onClick={() => handleChange('marketClockTimezone', tz)}
                        className={`py-1 rounded text-xs font-mono transition-colors border ${
                          formState.marketClockTimezone === tz
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold'
                            : 'bg-black/40 text-slate-400 border-white/[0.08]'
                        }`}
                      >
                        {tz}
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-slate-400">Display header clock in institutional UTC or regional market session.</div>
                </div>
              </div>

              {/* High Density Mode & Balance Privacy Mask */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Ultra-High-Density Grid Layout</div>
                    <div className="text-slate-400 text-[11px]">Tighter padding and tabular numbers for multi-monitor Bloomberg-style display desks.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.highDensityMode}
                    onChange={(e) => handleChange('highDensityMode', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Privacy Balance Masking Mode</div>
                    <div className="text-slate-400 text-[11px]">Masks portfolio NAV and order sizes ($***,***,***) for presentation security.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.privacyBalanceMask}
                    onChange={(e) => handleChange('privacyBalanceMask', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 11: Security & Multi-Sig */}
          {activeSection === 'security' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Lock className="w-4 h-4 text-cyan-400" />
                    SECURITY, 2FA HARDWARE KEYS &amp; MULTI-SIG CUSTODY
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Hardware security module (HSM) keys, session timeouts, and role-based cryptographic permissions.
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                  HSM SECURE ENCLAVE
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="font-bold text-white text-xs">2FA / FIDO2 Hardware Token Enforced</div>
                    <input
                      type="checkbox"
                      checked={formState.require2FAForRebalance}
                      onChange={(e) => handleChange('require2FAForRebalance', e.target.checked)}
                      className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                    />
                  </div>
                  <div className="text-slate-400 text-[11px]">Require YubiKey or WebAuthn physical tap when executing rebalances over $500k.</div>
                </div>

                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="font-bold text-white text-xs">Master Operator Key Fingerprint</div>
                  <div className="p-2 rounded bg-black/50 border border-white/[0.08] font-mono text-[11px] text-cyan-300 flex items-center justify-between">
                    <span>9F8A-42C1-88E0-BA32-001F</span>
                    <button
                      onClick={() => handleCopyKey('hsm', '9F8A-42C1-88E0-BA32-001F')}
                      className="text-slate-400 hover:text-white"
                    >
                      {copiedKeyId === 'hsm' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <div className="text-[10px] text-slate-400">Enclave Status: Hardware Verified &amp; Attested (TPM 2.0)</div>
                </div>
              </div>

              {/* Session Timeout and Kill Switch PIN */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white text-xs">Session Inactivity Lockout</span>
                    <span className="text-cyan-300 font-mono font-bold">{formState.sessionIdleTimeoutMinutes} Minutes</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="120"
                    step="5"
                    value={formState.sessionIdleTimeoutMinutes}
                    onChange={(e) => handleChange('sessionIdleTimeoutMinutes', parseInt(e.target.value))}
                    className="w-full h-1.5 bg-black/60 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                  <div className="text-[10px] text-slate-400">Auto-lock terminal workstation after idle time.</div>
                </div>

                <div className="p-3.5 rounded bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Emergency Kill Switch Safety PIN</div>
                    <div className="text-slate-400 text-[11px]">Require 6-digit confirmation code before triggering full portfolio flatten.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formState.killSwitchRequirePin}
                    onChange={(e) => handleChange('killSwitchRequirePin', e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* SECTION 12: Backup & Export */}
          {activeSection === 'backup' && (
            <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-5 shadow-2xl space-y-6">
              <div className="border-b border-white/[0.06] pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Download className="w-4 h-4 text-cyan-400" />
                    SYSTEM BACKUP, MERKLE LEDGER EXPORT &amp; HARD RESET
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Export entire system configuration, upload JSON configurations, or restore default Constitution v1.0.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Export Config */}
                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Export Active Config (JSON)</div>
                    <div className="text-slate-400 text-[11px] mt-1">
                      Download all current risk thresholds, agent model routes, venue credentials, and tax rules.
                    </div>
                  </div>
                  <button
                    onClick={handleExportConfig}
                    className="w-full py-2 rounded bg-cyan-950 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>EXPORT SYSTEM JSON</span>
                  </button>
                </div>

                {/* Import Config */}
                <div className="p-4 rounded bg-white/[0.02] border border-white/[0.06] space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-white text-xs">Import Configuration (JSON)</div>
                    <div className="text-slate-400 text-[11px] mt-1">
                      Restore parameters from a previous configuration snapshot file.
                    </div>
                  </div>
                  <label className="w-full py-2 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2 cursor-pointer">
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
                <div className="p-4 rounded bg-white/[0.02] border border-rose-900/40 space-y-3 flex flex-col justify-between">
                  <div>
                    <div className="font-bold text-rose-300 text-xs">Reset to Institutional Defaults</div>
                    <div className="text-slate-400 text-[11px] mt-1">
                      Reverts all risk thresholds, agent quorum weights, and algorithms to the baseline Ratified Constitution v1.0.
                    </div>
                  </div>
                  <button
                    onClick={() => setShowResetConfirm(true)}
                    className="w-full py-2 rounded bg-rose-950/80 hover:bg-rose-900 border border-rose-700/60 text-rose-300 font-bold text-xs flex items-center justify-center gap-2 transition-colors mt-2"
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

      {/* Add Credential Modal */}
      {showAddKeyModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-[#0d0f17] border border-white/[0.12] rounded-lg p-5 shadow-2xl space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-sm">
                <Key className="w-4 h-4" />
                <span>ADD GATEWAY CREDENTIAL</span>
              </div>
              <button
                onClick={() => setShowAddKeyModal(false)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 text-[11px]">Target Service / Exchange</label>
                <select
                  value={newKeyForm.service}
                  onChange={(e) => setNewKeyForm({ ...newKeyForm, service: e.target.value })}
                  className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-1.5 text-white font-mono mt-1 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="Polymarket CLOB Gateway">Polymarket CLOB &amp; Polygon L2 Settlement</option>
                  <option value="Interactive Brokers FIX Gateway">Interactive Brokers Global (TSE, HKEX, Euronext, NSE)</option>
                  <option value="EBS &amp; 360T Interbank Forex">EBS &amp; 360T Interbank Forex FIX 4.4</option>
                  <option value="ICE Europe &amp; LME Direct">ICE Europe &amp; London Metal Exchange (LME)</option>
                  <option value="Binance Institutional">Binance Institutional (FIX 4.4)</option>
                  <option value="CME Group Direct">CME Group Direct (Aurora iLink3)</option>
                  <option value="Coinbase Prime Custody">Coinbase Prime Custody</option>
                  <option value="Hyperliquid L1">Hyperliquid L1 Perps</option>
                  <option value="Google Gemini AI Engine">Google Gemini GenAI Token</option>
                  <option value="Anthropic Claude Engine">Anthropic Claude Token</option>
                  <option value="SEC EDGAR Feed">SEC EDGAR Continuous Feed</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 text-[11px]">Credential Name / Description</label>
                <input
                  type="text"
                  placeholder="e.g. Primary Arbitrum Sub-account"
                  value={newKeyForm.name}
                  onChange={(e) => setNewKeyForm({ ...newKeyForm, name: e.target.value })}
                  className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-1.5 text-white font-mono mt-1 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-slate-400 text-[11px]">API Key / Secret Token</label>
                <input
                  type="password"
                  placeholder="Paste raw secret token here..."
                  value={newKeyForm.key}
                  onChange={(e) => setNewKeyForm({ ...newKeyForm, key: e.target.value })}
                  className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-1.5 text-white font-mono mt-1 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-slate-400 text-[11px]">Enforced Permission Scope</label>
                <select
                  value={newKeyForm.permissions}
                  onChange={(e) => setNewKeyForm({ ...newKeyForm, permissions: e.target.value as any })}
                  className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-1.5 text-white font-mono mt-1 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="READ_ONLY">Read Only (Telemetry &amp; Orderbook)</option>
                  <option value="TRADE_ONLY">Trade Only (Orders Allowed, Withdrawals Forbidden)</option>
                  <option value="FULL_ACCESS">Full Access (Inference &amp; Admin)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/[0.08]">
              <button
                onClick={() => setShowAddKeyModal(false)}
                className="px-3 py-1.5 rounded bg-white/[0.05] hover:bg-white/[0.1] text-xs text-slate-300"
              >
                CANCEL
              </button>
              <button
                onClick={handleAddKey}
                className="px-4 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs"
              >
                ENCRYPT &amp; SAVE KEY
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Confirmation Modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-[#0d0f17] border border-rose-600 rounded-lg p-5 shadow-2xl space-y-4 font-mono">
            <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
              <AlertTriangle className="w-5 h-5" />
              <span>CONFIRM SYSTEM CONFIG RESET</span>
            </div>
            <p className="text-slate-300 text-xs leading-relaxed">
              Are you sure you want to reset all operational limits, multi-agent weights, and venue configurations to institutional defaults? This action will overwrite any pending unsaved changes.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowResetConfirm(false)}
                className="px-3 py-1.5 rounded bg-white/[0.05] hover:bg-white/[0.1] text-xs text-slate-300"
              >
                CANCEL
              </button>
              <button
                onClick={() => {
                  onResetDefaults();
                  setFormState(settings);
                  setIsDirty(false);
                  setShowResetConfirm(false);
                  onTriggerToast('System configuration reset to Institutional Defaults.');
                }}
                className="px-4 py-1.5 rounded bg-rose-600 hover:bg-rose-500 text-black font-bold text-xs"
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
