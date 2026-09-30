import React, { useState, useEffect } from 'react';
import { 
  Search, 
   
   
   
   
   
   
   
  ArrowRight,
  

} from 'lucide-react';
import { WorkspaceTab } from '../types';

interface CommandPaletteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (tab: WorkspaceTab) => void;
  onSelectSymbol?: (symbol: string) => void;
}

interface PaletteItem {
  id: string;
  category: 'NAVIGATION' | 'SYMBOLS' | 'AGENTS' | 'CONSTITUTION' | 'ACTIONS';
  title: string;
  subtitle?: string;
  action: () => void;
}

export const CommandPaletteModal: React.FC<CommandPaletteModalProps> = ({
  isOpen,
  onClose,
  onNavigate,
  onSelectSymbol,
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        // handled in parent or here
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const allItems: PaletteItem[] = [
    // Navigation
    { id: 'nav-overview', category: 'NAVIGATION', title: 'Go to Command Canvas', subtitle: 'Live investment state & trajectory', action: () => { onNavigate('overview'); onClose(); } },
    { id: 'nav-trading', category: 'NAVIGATION', title: 'Go to Live Trading & Charting Terminal', subtitle: 'Interactive TradingView Pro chart, L2 DOM book & Algorithmic Order Ticket', action: () => { onNavigate('trading'); onClose(); } },
    { id: 'nav-portfolio', category: 'NAVIGATION', title: 'Go to Portfolio Intelligence', subtitle: 'Positions, factor exposures, Kelly sizing', action: () => { onNavigate('portfolio'); onClose(); } },
    { id: 'nav-markets', category: 'NAVIGATION', title: 'Go to Market Intelligence', subtitle: 'Cross-asset regime & volatility surfaces', action: () => { onNavigate('markets'); onClose(); } },
    { id: 'nav-agents', category: 'NAVIGATION', title: 'Go to AI Agent Network', subtitle: 'Multi-agent debate & consensus engine', action: () => { onNavigate('agents'); onClose(); } },
    { id: 'nav-provenance', category: 'NAVIGATION', title: 'Go to Decision Provenance', subtitle: 'Lineage from source to execution fill', action: () => { onNavigate('provenance'); onClose(); } },
    { id: 'nav-risk', category: 'NAVIGATION', title: 'Go to Risk Command Center', subtitle: 'Continuous spectrum & firewall governor', action: () => { onNavigate('risk'); onClose(); } },
    { id: 'nav-execution', category: 'NAVIGATION', title: 'Go to Execution Workspace', subtitle: 'TWAP slicers & venue routing', action: () => { onNavigate('execution'); onClose(); } },
    { id: 'nav-models', category: 'NAVIGATION', title: 'Go to Model Governance', subtitle: 'MLflow registry, walk-forward validation', action: () => { onNavigate('models'); onClose(); } },
    { id: 'nav-accounting', category: 'NAVIGATION', title: 'Go to Accounting & Tax', subtitle: 'Double-entry ledger & compliance controller sign-off', action: () => { onNavigate('accounting'); onClose(); } },
    { id: 'nav-audit', category: 'NAVIGATION', title: 'Go to Audit & System Integrity', subtitle: 'Merkle hash chain & Constitution v1.0.0', action: () => { onNavigate('audit'); onClose(); } },
    { id: 'nav-system', category: 'NAVIGATION', title: 'Go to System Health', subtitle: '38/38 wired components & telemetry', action: () => { onNavigate('system'); onClose(); } },
    { id: 'nav-ds', category: 'NAVIGATION', title: 'Go to Design System Catalog', subtitle: 'Institutional UI component tokens', action: () => { onNavigate('design_system'); onClose(); } },
    { id: 'nav-settings', category: 'NAVIGATION', title: 'Go to System Settings & Config', subtitle: 'Risk limits, venue gateways, multi-agent tuning & governance', action: () => { onNavigate('settings'); onClose(); } },

    // Configuration Actions
    { id: 'act-new-order', category: 'ACTIONS', title: 'Dispatch New Algorithmic Order (TWAP / VWAP)', subtitle: 'Route slices through Smart Order Router (SOR)', action: () => { onNavigate('execution'); onClose(); } },
    { id: 'act-run-debate', category: 'ACTIONS', title: 'Run Live Multi-Agent Adversarial Debate', subtitle: 'Simulate LangGraph consensus on Fed, Earnings, or Oil shock', action: () => { onNavigate('provenance'); onClose(); } },
    { id: 'act-run-backtest', category: 'ACTIONS', title: 'Run Walk-Forward Backtester & Sensitivity Grid', subtitle: 'Simulate 1,000 bars with fractional Kelly tuning', action: () => { onNavigate('research'); onClose(); } },
    { id: 'act-stress-test', category: 'ACTIONS', title: 'Simulate Instant Macro Portfolio Shock', subtitle: 'Crypto flash crash, stagflation, or tech selloff', action: () => { onNavigate('portfolio'); onClose(); } },
    { id: 'act-risk-config', category: 'ACTIONS', title: 'Configure Drawdown Circuit Breakers', subtitle: 'Edit Tier 1, 2, and 3 emergency halt thresholds', action: () => { onNavigate('settings'); onClose(); } },
    { id: 'act-venue-config', category: 'ACTIONS', title: 'Manage Connected Exchange Gateways', subtitle: 'Binance, CME, Coinbase, Hyperliquid, Interactive Brokers', action: () => { onNavigate('settings'); onClose(); } },
    { id: 'act-agent-weights', category: 'ACTIONS', title: 'Calibrate Agent Reputation Weights', subtitle: 'Adjust LangGraph consensus voting distribution', action: () => { onNavigate('settings'); onClose(); } },
    { id: 'act-tax-method', category: 'ACTIONS', title: 'Change Tax Lot Optimization Method', subtitle: 'Switch between HIFO, FIFO, LIFO, and SpecID', action: () => { onNavigate('settings'); onClose(); } },
    { id: 'act-export-json', category: 'ACTIONS', title: 'Export Full System Configuration JSON', subtitle: 'Backup current operational parameters and risk limits', action: () => { onNavigate('settings'); onClose(); } },

    // Symbols
    { id: 'sym-btc', category: 'SYMBOLS', title: 'Inspect BTC/USD', subtitle: '$94,820.00 • Momentum Overweight', action: () => { onNavigate('portfolio'); if (onSelectSymbol) onSelectSymbol('BTC/USD'); onClose(); } },
    { id: 'sym-eth', category: 'SYMBOLS', title: 'Inspect ETH/USD', subtitle: '$3,410.50 • Staking Yield Accumulation', action: () => { onNavigate('portfolio'); if (onSelectSymbol) onSelectSymbol('ETH/USD'); onClose(); } },
    { id: 'sym-nvda', category: 'SYMBOLS', title: 'Inspect NVDA', subtitle: '$138.40 • Semi Supply Dispersion Long', action: () => { onNavigate('portfolio'); if (onSelectSymbol) onSelectSymbol('NVDA'); onClose(); } },
    { id: 'sym-spx', category: 'SYMBOLS', title: 'Inspect SPX', subtitle: '$5,820.00 • Trend Following Exposure', action: () => { onNavigate('portfolio'); if (onSelectSymbol) onSelectSymbol('SPX'); onClose(); } },

    // Agents
    { id: 'agt-macro', category: 'AGENTS', title: 'Agent: Macro Regime Specialist', subtitle: 'Confidence: 89.2% • Bias: Bull', action: () => { onNavigate('agents'); onClose(); } },
    { id: 'agt-challenger', category: 'AGENTS', title: 'Agent: Adversarial Challenger', subtitle: 'Confidence: 81.0% • Bias: Bear', action: () => { onNavigate('agents'); onClose(); } },
    { id: 'agt-risk', category: 'AGENTS', title: 'Agent: Risk Firewall Sentinel', subtitle: 'Confidence: 96.5% • Bias: Neutral', action: () => { onNavigate('agents'); onClose(); } },

    // Constitution
    { id: 'cst-drawdown', category: 'CONSTITUTION', title: 'Constitution §2.1: Tiered Drawdown Rule', subtitle: 'Halt trading when intraday drawdown touches 3.00%', action: () => { onNavigate('audit'); onClose(); } },
    { id: 'cst-debate', category: 'CONSTITUTION', title: 'Constitution §3.4: Adversarial Debate Requirement', subtitle: 'All capital allocations > $1M require Challenger cross-examination', action: () => { onNavigate('audit'); onClose(); } },
  ];

  const filteredItems = query.trim() === ''
    ? allItems
    : allItems.filter(item => 
        item.title.toLowerCase().includes(query.toLowerCase()) ||
        item.subtitle?.toLowerCase().includes(query.toLowerCase()) ||
        item.category.toLowerCase().includes(query.toLowerCase())
      );

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/75 backdrop-blur-md flex items-start justify-center pt-20 px-4 animate-fade-in font-mono">
      <div className="w-full max-w-2xl bg-[#0d0f17] border border-white/[0.12] rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Input Bar */}
        <div className="p-3.5 border-b border-white/[0.08] flex items-center gap-3">
          <Search className="w-5 h-5 text-cyan-400 shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="Type a command, instrument, agent thesis, or constitution clause..."
            className="w-full bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none font-sans"
            autoFocus
          />
          <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-slate-400">
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div className="max-h-96 overflow-y-auto p-2 space-y-1">
          {filteredItems.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-xs">
              No matching institutional commands or symbols found.
            </div>
          ) : (
            filteredItems.map((item, idx) => (
              <div
                key={item.id}
                onClick={item.action}
                className={`p-2.5 rounded flex items-center justify-between cursor-pointer transition-colors ${
                  idx === selectedIndex 
                    ? 'bg-cyan-950/40 border border-cyan-700/50 text-white shadow-sm' 
                    : 'text-slate-300 hover:bg-white/[0.04]'
                }`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono px-1 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06] uppercase">
                      {item.category}
                    </span>
                    <span className="text-xs font-semibold text-slate-100">{item.title}</span>
                  </div>
                  {item.subtitle && (
                    <div className="text-[11px] text-slate-400 mt-0.5 pl-14 truncate max-w-lg">
                      {item.subtitle}
                    </div>
                  )}
                </div>

                <ArrowRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              </div>
            ))
          )}
        </div>

        {/* Footer info */}
        <div className="p-2 border-t border-white/[0.06] bg-black/40 text-[10px] text-slate-500 flex items-center justify-between px-3">
          <span>Navigate with <strong className="text-slate-400">↑ ↓</strong> • Select with <strong className="text-slate-400">ENTER</strong></span>
          <span>AIOS-0X GLOBAL DISCOVERY ENGINE</span>
        </div>
      </div>
    </div>
  );
};
