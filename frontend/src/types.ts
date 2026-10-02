export type AutonomyLevel = 'MANUAL' | 'ASSISTED' | 'SUPERVISED' | 'AUTONOMOUS' | 'EMERGENCY_HALT';
export type ExecutionMode = 'PAPER' | 'LIVE';
export type MarketState = 'OPEN' | 'CLOSED' | 'PRE_MARKET' | 'POST_MARKET';

/**
 * Every workspace tab, as a runtime value rather than only a type.
 *
 * The union alone could not be checked: a test cannot iterate over a type, so the
 * architecture grouping gate could only assert that the workspaces it knows about are
 * grouped -- never that every tab is grouped. A seventeenth tab added to the union
 * would have passed silently. Deriving the type from this array means the two cannot
 * drift apart, so the gate can demand totality.
 */
export const WORKSPACE_TABS = [
  'overview',
  'trading',
  'portfolio',
  'markets',
  'research',
  'agents',
  'strategies',
  'certification',
  'execution',
  'risk',
  'models',
  'provenance',
  'accounting',
  'financial',
  'audit',
  'system',
  'chat',
  'design_system',
  'settings',
] as const;

export type WorkspaceTab = typeof WORKSPACE_TABS[number];

export type TimelineEventType = 
  | 'AGENT_CONSENSUS'
  | 'RISK_REDUCTION'
  | 'POSITION_OPENED'
  | 'REGIME_SHIFT'
  | 'MODEL_PROMOTED'
  | 'HUMAN_APPROVAL'
  | 'EXECUTION_COMPLETED';

export interface TimelineEvent {
  id: string;
  time: string;
  type: TimelineEventType;
  title: string;
  description: string;
  impactScore?: number;
  agent?: string;
  symbol?: string;
}

export interface TrajectoryDataPoint {
  time: string;
  nav: number; // e.g. 142890450
  intradayPnl: number;
  benchmark: number; // e.g. S&P / Hedge Fund index
  drawdownPct: number;
  capitalUtilizationPct: number;
  event?: TimelineEvent;
}

export interface IntelligenceItem {
  id: string;
  headline: string;
  detail: string;
  confidencePct: number;
  supportAgents: number;
  counterAgents: number;
  riskImpact: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  action: 'WATCH' | 'ACCUMULATE' | 'TRIM' | 'REBALANCE' | 'HEDGE';
  timestamp: string;
  category: 'MACRO' | 'CRYPTO' | 'EQUITIES' | 'VOLATILITY' | 'SENTIMENT';
}

export interface AllocationSegment {
  id: string;
  name: string;
  color: string;
  currentExposurePct: number;
  targetExposurePct: number;
  notionalUsd: number;
  riskContributionPct: number;
  correlation: number;
  drawdownContributionPct: number;
}

export interface RiskSpectrum {
  currentDrawdownPct: number;
  warningThresholdPct: number;
  reductionThresholdPct: number;
  emergencyHaltPct: number;
  positionConcentrationPct: number;
  maxPositionConcentrationPct: number;
  classExposurePct: number;
  maxClassExposurePct: number;
  correlationExposure: number;
  maxCorrelationExposure: number;
  var95IntradayPct: number;
  cvar99Pct: number;
  leverage: string; // 1.00x Cash Only
  marginStatus: string;
}

export type AgentRole = 
  | 'MACRO' 
  | 'TECHNICAL' 
  | 'FUNDAMENTAL' 
  | 'SENTIMENT' 
  | 'RISK' 
  | 'EXECUTION' 
  | 'CHALLENGER' 
  | 'VERIFIER'
  | 'POLYMARKET_ARB'
  | 'GLOBAL_MACRO_FX'
  | 'COMMODITY_SPECIALIST'
  | 'CROSS_BORDER_EQUITIES';

export interface AgentNode {
  id: string;
  name: string;
  role: AgentRole;
  reputationScore: number; // 0.0 to 1.0 (or up to 1.5)
  confidencePct: number;
  currentThesis: string;
  bias: 'BULL' | 'BEAR' | 'NEUTRAL';
  recentAccuracyPct: number;
  status: 'ONLINE' | 'DELIBERATING' | 'CONSENSUS_REACHED' | 'STANDBY' | 'CHALLENGING';
  lastEvaluated: string;
  latencyMs: number;
  modelsUsed: string[];
}

export interface ProvenanceTrace {
  executionId: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  fillPrice: number;
  timestamp: string;
  slippageBps: number;
  decision: {
    decisionId: string;
    rationale: string;
    consensusScore: number;
    decisionAgent: string;
    riskCheckPassed: boolean;
    firewallDigest: string;
  };
  strategy: {
    strategyId: string;
    name: string;
    family: string;
    targetSharpe: number;
    allocatedCapitalUsd: number;
  };
  hypothesis: {
    hypothesisId: string;
    title: string;
    formalStatement: string;
    verificationStatus: 'SUPPORTED' | 'CONFIRMED' | 'TESTING';
  };
  evidence: {
    evidenceId: string;
    claims: string[];
    counterClaims: string[];
    confidence: number;
  };
  source: {
    sourceType: string;
    feed: string;
    rawPayloadHash: string;
    signatureVerified: boolean;
  };
  integrityHash: string; // SHA-256
}

export interface ExecutionOrder {
  id: string;
  time: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  notionalUsd: number;
  orderState: 'FILLED' | 'ROUTING' | 'PARTIAL' | 'CANCELLED' | 'VERIFYING';
  fillPrice: number;
  slippageBps: number;
  strategy: string;
  agent: string;
  riskState: 'COMPLIANT' | 'WARNING' | 'OVERRIDDEN';
  venue: string;
}

export type AssetClass = 
  | 'GLOBAL_EQUITY' 
  | 'US_EQUITY' 
  | 'POLYMARKET' 
  | 'COMMODITY' 
  | 'FX' 
  | 'CRYPTO' 
  | 'RATES' 
  | 'EQUITY';

export interface MarketRegimeItem {
  symbol: string;
  name: string;
  category: 'POLYMARKET' | 'COMMODITY' | 'FX' | 'GLOBAL_EQUITY' | 'US_EQUITY' | 'CRYPTO' | 'MACRO' | 'VOLATILITY' | 'EQUITY';
  price: number;
  change24hPct: number;
  trend: 'STRONG_BULL' | 'BULL' | 'SIDEWAYS' | 'BEAR' | 'STRONG_BEAR';
  volatility: 'LOW' | 'NORMAL' | 'HIGH' | 'EXTREME';
  momentum: number; // e.g. +78 or -34
  regime: string; // e.g. "Expansionary", "Mean-Reverting", "Risk-Off"
  confidencePct: number;
  sparkline: number[];
  country?: string;
  countryCode?: string;
  exchange?: string;
  localCurrency?: string;
  polymarketData?: {
    question: string;
    impliedOddsPct: number;
    modelBayesianProbPct: number;
    edgeBps: number;
    volume24hUsd: number;
    resolutionDate: string;
    yesPrice: number;
    noPrice: number;
  };
  fxData?: {
    pair: string;
    rateDifferentialPct: number;
    centralBankDivergence: string;
    carryAnnualYieldPct: number;
  };
  commodityData?: {
    termStructure: 'CONTANGO' | 'BACKWARDATION';
    rollYieldPct: number;
    inventoryStress: 'TIGHT' | 'BALANCED' | 'SURPLUS';
    deliveryHub: string;
  };
}

export type ModelLifecycleState = 
  | 'INIT' 
  | 'TRAIN' 
  | 'EVALUATE' 
  | 'PROMOTE' 
  | 'DEPLOY' 
  | 'MONITOR' 
  | 'REPUTATION' 
  | 'RETIRE';

export interface ModelGovernanceItem {
  id: string;
  name: string;
  version: string;
  architecture: string;
  status: ModelLifecycleState;
  evaluationScore: number;
  sharpeRatio: number;
  winRatePct: number;
  maxDrawdownPct: number;
  reputation: number;
  promotionState: 'PROMOTED_PRODUCTION' | 'BENCHMARK_CANDIDATE' | 'SHADOW_TESTING' | 'DEPRECATED';
  trainedOnBars: number;
  latencyP95Ms: number;
}

export interface Position {
  id: string;
  symbol: string;
  name: string;
  assetClass: AssetClass;
  side: 'LONG' | 'SHORT';
  size: number;
  entryPrice: number;
  markPrice: number;
  notionalUsd: number;
  unrealizedPnlUsd: number;
  unrealizedPnlPct: number;
  exposurePct?: number;
  stopLossPrice?: number;
  takeProfitPrice?: number;
  strategy?: string;
  originatingAgent?: string;
  varContributionUsd?: number;
  liquidityTier?: string;
  country?: string;
  countryCode?: string;
  exchange?: string;
  localCurrency?: string;
  polymarketOddsPct?: number;
  eventOutcomeDate?: string;
}

export interface PositionItem {
  symbol: string;
  name: string;
  assetClass: AssetClass;
  side: 'LONG' | 'SHORT';
  quantity: number;
  entryPrice: number;
  markPrice: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  exposurePct: number;
  stopLoss: number;
  takeProfit: number;
  allocationUsd: number;
  agentOwner: string;
  strategyOwner: string;
  country?: string;
  countryCode?: string;
  exchange?: string;
}

export interface SystemComponent {
  id: string;
  name: string;
  plane: 'Data Plane' | 'Control Plane' | 'Execution Plane' | 'Observability' | 'Governance';
  status: 'NOMINAL' | 'DEGRADED' | 'BENCHMARKING';
  latencyMs: number;
  uptimePct: number;
  memoryMb: number;
  version: string;
}

export interface AuditRecord {
  id?: string;
  seq?: number;
  blockHeight?: number;
  eventType?: string;
  timestamp: string;
  kind?: string;
  refId?: string;
  actor: string;
  hash?: string;
  currentHash?: string;
  prevHash: string;
  verified: boolean;
  summary?: string;
  actionSummary?: string;
  payload?: any;
}

export interface VenueConfig {
  id: string;
  name: string;
  enabled: boolean;
  gatewayType: 'FIX_DIRECT' | 'REST_WS' | 'ON_CHAIN_L1' | 'TWS_API';
  endpoint: string;
  latencyMs: number;
  status: 'CONNECTED' | 'DISCONNECTED' | 'STANDBY';
  apiPermission: 'READ_WRITE' | 'READ_ONLY';
  apiKeyMasked: string;
  ipWhitelistVerified: boolean;
}

export interface SystemSettings {
  // Autonomy & Governance
  autonomyLevel: AutonomyLevel;
  defaultExecutionMode: ExecutionMode;
  multiSigThresholdUsd: number;
  require2FAForRebalance: boolean;
  emergencyHaltDrawdownPct: number;
  autoDeescalateOnAnomaly: boolean;

  // Risk Firewall Limits
  warningDrawdownPct: number;
  deriskDrawdownPct: number;
  maxPositionConcentrationPct: number;
  maxClassExposurePct: number;
  maxGrossLeverage: number;
  maxCorrelationCap: number;
  overnightDerisking: boolean;
  var95DailyLimitUsd: number;

  // Multi-Agent Debate & Consensus
  minConsensusThresholdPct: number;
  maxDebateRounds: number;
  mandatoryChallengerGate: boolean;
  dynamicReputationWeighting: boolean;
  agentLearningRate: number;
  macroAgentBaseWeight: number;
  quantAgentBaseWeight: number;
  sentimentAgentBaseWeight: number;
  riskSentinelBaseWeight: number;

  // Execution & SOR
  defaultAlgorithm: 'TWAP' | 'VWAP' | 'POV' | 'ICEBERG' | 'IMPLEMENTATION_SHORTFALL';
  maxSlippageBps: number;
  twapWindowMinutes: number;
  preTradeLatencyTimeoutMs: number;
  enableDarkPoolCrossing: boolean;
  venues: VenueConfig[];

  // Accounting, Tax & Compliance
  taxLotMethod: 'HIFO' | 'FIFO' | 'LIFO' | 'SpecID';
  capGainsProvisionRatePct: number;
  dailyControllerSignOffRequired: boolean;
  washSaleGuard: boolean;
  autoTaxLossHarvesting: boolean;
  taxLossHarvestMinLossUsd: number;
  baseReportingCurrency: 'USD' | 'EUR' | 'GBP' | 'CHF' | 'SGD' | 'JPY';
  fiscalYearEnd: string;

  // Additional Autonomy & Time Governance
  tradingWindowMode: '24_7_GLOBAL' | 'MARKET_HOURS_NYSE' | 'LONDON_NY_OVERLAP';
  rebalanceCooldownMinutes: number;

  // Additional Tail Risk Guardrails
  expectedShortfallCapPct: number;
  maxSectorBetaCap: number;

  // AI Models & Inference Gatekeeper
  macroAgentModel: string;
  quantAgentModel: string;
  sentimentAgentModel: string;
  riskSentinelModel: string;
  inferenceTemperature: number;
  promptSanitizerActive: boolean;

  // Data Feeds & Oracles
  oracleProvider: 'CHAINLINK_PYTH_DUAL' | 'CHAINLINK_ONLY' | 'PYTH_ONLY' | 'SWITCHBOARD';
  oracleStalenessMaxSec: number;
  maxOracleDeviationBps: number;

  // On-Chain Execution & MEV Protection
  gasMaxGweiCap: number;
  flashbotsMevProtection: boolean;

  // Backtesting & Monte Carlo Stress Testing
  backtestLookbackYears: number;
  monteCarloSimulationsCount: number;
  stressTestScenario: 'COVID_CRASH_2020' | 'GFC_2008' | 'TERRA_FTX_2022' | 'RATE_HIKE_500BPS' | 'CUSTOM';

  // Security, Hardware Keys & Session
  hardwareKeyFido2Required: boolean;
  sessionIdleTimeoutMinutes: number;
  killSwitchRequirePin: boolean;

  // Alerts & Notifications
  alertOnDrawdownWarning: boolean;
  alertOnDrawdownDerisk: boolean;
  alertOnLargeFills: boolean;
  alertOnDebateDeadlock: boolean;
  alertOnMerkleBlock: boolean;
  acousticAlerts: 'SUBTLE' | 'SONAR' | 'MUTED';
  webhookUrl: string;
  telegramAlertsEnabled: boolean;
  telegramChatIdMasked: string;
  pagerDutyIntegration: boolean;

  // Display & UI Preferences
  // NOTE: appearance (theme + accent) is deliberately NOT a field here. It is client-local,
  // held in localStorage and applied by `lib/theme.ts`. It was previously an `accentTheme`
  // field the backend never defined, so it round-tripped through a PUT as an unknown key
  // while marking the settings form dirty — "unsaved changes" for a change already applied
  // and visible. `theme.test.ts` asserts it stays out, so it cannot quietly return.
  refreshRateMs: number;
  marketClockTimezone: 'UTC' | 'EST' | 'GMT' | 'JST';
  privacyBalanceMask: boolean;

  // TradingView Technical Charting API & Datafeed
  tradingViewApiEnabled: boolean;
  tradingViewApiKey: string;
  tradingViewClientId: string;
  tradingViewDatafeedUrl: string;
  tradingViewDefaultTheme: 'dark' | 'light';
  tradingViewInterval: '1' | '5' | '15' | '60' | '240' | 'D' | 'W';
  tradingViewChartType: 'CANDLES' | 'HEIKIN_ASHI' | 'LINE' | 'AREA';
  tradingViewWebhooksEnabled: boolean;
  tradingViewWebhookSecret: string;
  tradingViewShowVolume: boolean;
  tradingViewShowIndicators: boolean;
  tradingViewActiveIndicators: string[];
  tradingViewSymbolMapping: Record<string, string>;
}

export type DebateStance = 
  | 'PROPOSE_LONG' 
  | 'PROPOSE_SHORT' 
  | 'CHALLENGE_RISK' 
  | 'CHALLENGE_VALUATION' 
  | 'EVIDENTIARY_AUDIT' 
  | 'REBUTTAL' 
  | 'FIREWALL_VERIFICATION' 
  | 'SUPERMAJORITY_SYNTHESIS';

export interface DebateEvidenceItem {
  id: string;
  claim: string;
  source: string;
  dataType: 'ORACLE' | 'FILING' | 'ORDERBOOK' | 'MACRO_REPORT' | 'SENTIMENT' | 'ON_CHAIN' | 'VOL_SURFACE' | 'PHYSICAL_AUDIT';
  metricValue?: string;
  verificationHash?: string;
  isVerified: boolean;
  confidenceScore: number;
}

export interface DebateTurn {
  id: string;
  turnNumber: number;
  timestamp: string;
  agentId: string;
  agentName: string;
  agentRole: AgentRole;
  modelVersion: string;
  reputationScore: number;
  stance: DebateStance;
  thesis: string;
  confidencePct: number;
  weightScore: number; // calculated from reputation and confidence
  evidence: DebateEvidenceItem[];
  counterArgumentsAddressed?: string[];
  suggestedRiskAdjustment?: {
    maxNotionalUsd?: number;
    stopLossPrice?: number;
    sizingAdjustmentPct?: number;
    executionVenue?: string;
    executionMethod?: string;
  };
}

export interface DebateResolution {
  summary: string;
  keyCompromise: string;
  outcomeStatus: 'APPROVED_AND_EXECUTED' | 'APPROVED_WITH_HAIRCUT' | 'REJECTED_BY_FIREWALL' | 'UNDER_ACTIVE_DELIBERATION';
  finalApprovedNotionalUsd: number;
  consensusScorePct: number;
  thresholdRequiredPct: number;
  approvedParameters: {
    symbol: string;
    side: 'LONG' | 'SHORT' | 'HEDGE';
    size: number;
    fillPriceTarget: number;
    stopLoss: number;
    takeProfit: number;
    venue: string;
    riskFirewallPassed: number;
    riskFirewallTotal: number;
  };
  merkleProofDigest: string;
  auditSignature: string;
}

export interface DebateSession {
  id: string;
  tradeId: string;
  symbol: string;
  name: string;
  assetClass: AssetClass;
  side: 'LONG' | 'SHORT' | 'HEDGE';
  proposedNotionalUsd: number;
  initiatedAt: string;
  resolvedAt?: string;
  status: 'RESOLVED_APPROVED' | 'RESOLVED_HAIRCUT' | 'ACTIVE_DELIBERATING' | 'REJECTED_RISK';
  consensusScorePct: number;
  thresholdRequiredPct: number;
  roundsCount: number;
  participantsCount: number;
  proposingAgent: string;
  leadChallenger: string;
  riskValidator: string;
  resolution: DebateResolution;
  turns: DebateTurn[];
}



