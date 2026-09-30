/**
 * Navigation registry. Every AIOS workspace capability from §6 is mapped here
 * to a nav item with icon, label, group, and React component. The rail shows
 * these in group order with separators; the mobile bottom nav mirrors the
 * first 8 for quick access.
 */
import { ICONS } from "./nav";
import type { NavItem } from "./nav";

// — trade group
import { CommandDeck } from "../features/deck/CommandDeck";
import { PortfolioPage } from "../features/trade/Portfolio";
import { PositionsPage } from "../features/trade/Positions";
import { OrdersPage } from "../features/trade/Orders";
import { ExecutionsPage } from "../features/trade/Executions";
import { OpportunitiesPage } from "../features/trade/Opportunities";
import { ApprovalsPage } from "../features/safety/Approvals";

// — intelligence group
import { RiskCenterPage } from "../features/safety/RiskCenter";
import { OperationsCenterPage } from "../features/safety/OperationsCenter";
import { AgentNetworkPage } from "../features/intel/Intelligence";
import { GlobalEventsPage } from "../features/intel/Intelligence";
import { AlertsPage } from "../features/intel/Intelligence";

// — research group
import { KnowledgePage } from "../features/research/Research";
import { StrategiesPage } from "../features/research/Strategies";
import { ModelsPage } from "../features/research/Research";
import { ResearchQualityPage, MemoryPage } from "../features/research/Research";

// — finance group
import { PnlPage } from "../features/finance/Finance";
import { AccountingPage } from "../features/finance/Finance";
import { TaxReviewPage } from "../features/finance/Finance";
import { AuditPage } from "../features/system/AuditTrail";

// — durable financial kernel (V1-A.2)
import {
  BookOfRecordPage,
  CashReservationsPage,
  EventDeliveryPage,
  FinancialHealthPage,
  FillsPage,
  ReconciliationPage,
} from "../features/kernel/Kernel";

// — system group
import { SettingsPage } from "../features/system/Settings";
import { ConsolePage } from "../features/system/Console";
import { PlatformEventsPage } from "../features/intel/Intelligence";

export const NAV_ITEMS: NavItem[] = [
  // — trade
  { id: "deck",       label: "Command Deck",       icon: ICONS.deck,       group: "trade",    component: (p) => <CommandDeck {...p} /> },
  { id: "portfolio",  label: "Portfolio",           icon: ICONS.wallet,     group: "trade",    component: () => <PortfolioPage /> },
  { id: "positions",  label: "Positions",           icon: ICONS.layers,    group: "trade",    component: () => <PositionsPage /> },
  { id: "orders",     label: "Orders & Tape",       icon: ICONS.swap,      group: "trade",    component: () => <OrdersPage /> },
  { id: "executions", label: "Decisions",           icon: ICONS.target,    group: "trade",    component: () => <ExecutionsPage /> },
  { id: "opportunities", label: "Opportunities",    icon: ICONS.flask,     group: "trade",    component: () => <OpportunitiesPage /> },
  { id: "approvals",  label: "Approvals",           icon: ICONS.check,     group: "trade",    component: () => <ApprovalsPage /> },
  // — intelligence
  { id: "risk",       label: "Risk & Safety",       icon: ICONS.shield,    group: "intel",    component: () => <RiskCenterPage /> },
  { id: "ops",        label: "Operations",          icon: ICONS.ops,       group: "intel",    component: () => <OperationsCenterPage /> },
  { id: "agents",     label: "Agent Network",       icon: ICONS.agents,    group: "intel",    component: () => <AgentNetworkPage /> },
  { id: "events",     label: "Global Events",       icon: ICONS.globe,     group: "intel",    component: () => <GlobalEventsPage /> },
  { id: "alerts",     label: "Alerts",              icon: ICONS.bell,      group: "intel",    component: () => <AlertsPage /> },
  // — research
  { id: "knowledge",  label: "Hypotheses",          icon: ICONS.book,      group: "research", component: () => <KnowledgePage /> },
  { id: "strategies", label: "Strategies",          icon: ICONS.ledger,    group: "research", component: () => <StrategiesPage /> },
  { id: "models",     label: "Models",              icon: ICONS.chip,      group: "research", component: () => <ModelsPage /> },
  { id: "research",   label: "Research Quality",    icon: ICONS.flask,     group: "research", component: () => <ResearchQualityPage /> },
  { id: "memory",     label: "Memory",              icon: ICONS.book,      group: "research", component: () => <MemoryPage /> },
  { id: "platform",   label: "Platform Events",     icon: ICONS.globe,     group: "research", component: () => <PlatformEventsPage /> },
  // — finance
  { id: "book",       label: "Book of Record",      icon: ICONS.book,      group: "finance",  component: () => <BookOfRecordPage /> },
  { id: "fills",      label: "Fills",               icon: ICONS.layers,    group: "finance",  component: () => <FillsPage /> },
  { id: "cash",       label: "Cash & Reservations", icon: ICONS.wallet,    group: "finance",  component: () => <CashReservationsPage /> },
  { id: "recon",      label: "Reconciliation",      icon: ICONS.scale,     group: "finance",  component: () => <ReconciliationPage /> },
  { id: "kernel",     label: "Financial Health",    icon: ICONS.shield,    group: "finance",  component: () => <FinancialHealthPage /> },
  { id: "delivery",   label: "Event Delivery",      icon: ICONS.swap,      group: "finance",  component: () => <EventDeliveryPage /> },
  { id: "pnl",        label: "P&L",                 icon: ICONS.pulse,     group: "finance",  component: () => <PnlPage /> },
  { id: "accounting", label: "Accounting",          icon: ICONS.ledger,    group: "finance",  component: () => <AccountingPage /> },
  { id: "tax",        label: "Tax & Review",        icon: ICONS.scale,     group: "finance",  component: () => <TaxReviewPage /> },
  { id: "audit",      label: "Audit Trail",         icon: ICONS.audit,     group: "finance",  component: () => <AuditPage /> },
  // — system
  { id: "settings",   label: "Settings",            icon: ICONS.gear,      group: "system",   component: () => <SettingsPage /> },
  { id: "console",    label: "Operator Console",    icon: ICONS.term,      group: "system",   component: () => <ConsolePage /> },
];
