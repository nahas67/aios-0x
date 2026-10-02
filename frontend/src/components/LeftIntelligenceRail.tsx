import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  PieChart, 
  TrendingUp, 
  CandlestickChart,
  BrainCircuit, 
  Users2, 
  GitFork, 
  Zap, 
  ShieldAlert, 
  ShieldCheck, 
  Binary, 
  Network, 
  ReceiptText, 
  Landmark, 
  FileCheck2, 
  Server, 
  Palette,
  Settings as SettingsIcon,
  ChevronRight,
  ChevronLeft
} from 'lucide-react';
import { WorkspaceTab } from '../types';
import { buildNavSections } from '../lib/architectureLayers';

interface LeftIntelligenceRailProps {
  activeTab: WorkspaceTab;
  onSelectTab: (tab: WorkspaceTab) => void;
  /** Live count from /approvals — badge hidden while unknown. */
  pendingApprovalsCount?: number | null;
  /** Live count from /risk compliance alerts + /alerts — badge hidden while unknown. */
  activeRiskWarnings?: number | null;
  /** Live count from /agents — badge hidden while unknown. */
  agentsCount?: number | null;
  /** Live count from /strategies — badge hidden while unknown. */
  strategiesCount?: number | null;
  /** Live count from /knowledge — badge hidden while unknown. */
  researchCount?: number | null;
  /** Live "wired/total" from /health components — badge hidden while unknown. */
  systemWired?: string | null;
}

interface NavItemConfig {
  id: WorkspaceTab;
  label: string;
  icon: React.ElementType;
  badge?: string | number;
  badgeColor?: string;
  category?: string;
}

export const LeftIntelligenceRail: React.FC<LeftIntelligenceRailProps> = ({
  activeTab,
  onSelectTab,
  pendingApprovalsCount = null,
  activeRiskWarnings = null,
  agentsCount = null,
  strategiesCount = null,
  researchCount = null,
  systemWired = null,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const countBadge = (n: number | null | undefined): string | number | undefined =>
    n !== null && n !== undefined && n > 0 ? n : undefined;

  /**
   * One nav row. Extracted so the §2 grouping can decide the ORDER without the row
   * markup being duplicated inside the grouping loop — the previous shape inlined the
   * button into a flat `.map()`, which left nowhere to put a group heading.
   */
  const renderNavItem = (item: NavItemConfig) => {
    const Icon = item.icon;
    const isActive = activeTab === item.id;

    return (
      <button
        key={item.id}
        onClick={() => onSelectTab(item.id)}
        className={`group w-full flex items-center gap-2.5 px-2 py-2 rounded transition-all text-left relative ${
          isActive
            ? 'bg-info-bg text-accent font-medium border border-accent shadow-[0_0_12px_rgba(0,240,255,0.12)]'
            : 'text-text-muted hover:text-text-strong hover:bg-surface-veil border border-transparent'
        }`}
        title={!isExpanded ? item.label : undefined}
      >
        {/* Active bar */}
        {isActive && (
          <span className="absolute left-0 top-1 bottom-1 w-0.5 bg-accent rounded-r shadow-[0_0_6px_var(--color-accent)]" />
        )}

        <div className="flex items-center justify-center shrink-0 w-6 h-6">
          <Icon
            className={`w-4 h-4 transition-transform group-hover:scale-105 ${
              isActive ? 'text-accent' : 'text-text-muted group-hover:text-text-strong'
            }`}
          />
        </div>

        {/* Label (Visible on hover expansion) */}
        <span
          className={`text-[12px] whitespace-nowrap overflow-hidden transition-all duration-150 ${
            isExpanded ? 'opacity-100 translate-x-0 w-auto' : 'opacity-0 -translate-x-2 w-0 hidden'
          }`}
        >
          {item.label}
        </span>

        {/* Badges */}
        {item.badge && (
          <span
            className={`ml-auto text-[9px] font-mono px-1 rounded border leading-tight ${
              item.badgeColor === 'amber'
                ? 'bg-warning-bg text-warning border-warning'
                : item.badgeColor === 'cyan'
                ? 'bg-info-bg text-accent border-accent'
                : item.badgeColor === 'violet'
                ? 'bg-violet text-violet border-violet'
                : 'bg-surface-veil text-text-muted border-border-subtle'
            } ${!isExpanded ? 'absolute top-1 right-1 px-0.5 text-[8px]' : ''}`}
          >
            {item.badge}
          </span>
        )}
      </button>
    );
  };

  const navItems: NavItemConfig[] = [
    { id: 'overview', label: 'Command Canvas', icon: LayoutDashboard },
    { id: 'trading', label: 'Live Trading', icon: CandlestickChart },
    { id: 'portfolio', label: 'Portfolio', icon: PieChart },
    { id: 'markets', label: 'Markets', icon: TrendingUp },
    { id: 'research', label: 'Research', icon: BrainCircuit, badge: countBadge(researchCount) },
    { id: 'agents', label: 'Agents', icon: Users2, badge: countBadge(agentsCount), badgeColor: 'cyan' },
    { id: 'strategies', label: 'Strategies', icon: GitFork, badge: countBadge(strategiesCount) },
    { id: 'certification', label: 'Certification', icon: ShieldCheck },
    { id: 'execution', label: 'Execution', icon: Zap },
    {
      id: 'risk',
      label: 'Risk',
      icon: ShieldAlert,
      badge: countBadge(activeRiskWarnings),
      badgeColor: 'amber'
    },
    { id: 'models', label: 'Models', icon: Binary },
    { id: 'provenance', label: 'Provenance', icon: Network },
    {
      id: 'accounting',
      label: 'Accounting',
      icon: ReceiptText,
      badge: countBadge(pendingApprovalsCount),
      badgeColor: 'violet'
    },
    { id: 'financial', label: 'Financial Kernel', icon: Landmark },
    { id: 'audit', label: 'Audit', icon: FileCheck2 },
    { id: 'system', label: 'System', icon: Server, badge: systemWired ?? undefined },
    { id: 'design_system', label: 'Design System', icon: Palette },
    { id: 'settings', label: 'Settings', icon: SettingsIcon }
  ];

  return (
    <aside
      onMouseEnter={() => setIsExpanded(true)}
      onMouseLeave={() => setIsExpanded(false)}
      className={`fixed left-0 top-11 bottom-0 z-30 bg-[var(--color-surface-rail)] border-r border-border-subtle flex flex-col justify-between transition-all duration-200 select-none ${
        isExpanded ? 'w-48 shadow-[8px_0_24px_rgba(0,0,0,0.6)]' : 'w-14'
      }`}
    >
      {/* Top Nav List, ordered by ARCHITECTURE.txt section 2's layers rather than by the
          order the items happened to be declared in. `architectureLayers.ts` owns the
          order and the grouping; this file owns only the icons, labels and badges. */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden py-2.5 px-1.5 space-y-1">
        {(() => {
          // Ordering and grouping are `buildNavSections`' job, not this file's: it is
          // pure and tested, and the one bug that matters here — an item quietly
          // vanishing from the nav — is invisible in JSX and obvious in a test.
          const sections = buildNavSections(navItems);

          return sections.map((section) => (
            <div key={section.label} className="space-y-1">
              {/* Layer headers only when expanded: the collapsed rail is 14px wide, and a
                  heading reduced to a stray glyph there is noise, not information. */}
              {isExpanded && (
                <div className="px-2 pt-2 pb-0.5 text-[9px] font-mono uppercase tracking-wider text-text-subtle truncate">
                  {section.label}
                </div>
              )}
              {section.items.map((item) => renderNavItem(item))}
            </div>
          ));
        })()}
      </div>

      {/* Rail Footer Toggle */}
      <div className="p-2 border-t border-border-subtle text-text-subtle flex items-center justify-between text-[11px]">
        {isExpanded ? (
          <div className="flex items-center justify-between w-full px-1">
            <span className="font-mono text-[10px] text-text-subtle uppercase tracking-wider">EXPANDED</span>
            <button 
              onClick={() => setIsExpanded(false)}
              className="text-text-muted hover:text-text-strong"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="w-full flex justify-center py-1">
            <button 
              onClick={() => setIsExpanded(true)}
              className="text-text-subtle hover:text-text"
              title="Expand rail"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};
