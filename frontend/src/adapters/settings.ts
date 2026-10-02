/**
 * settingsAdapter: GET /api/v1/settings/v1 → versioned SystemSettings.
 *
 * Backend: {available:true, version, settings} (empty object at version 0)
 * or {available:false, reason}. A `payload` key is accepted tolerantly for
 * forward-compat. A partial blob merges over EMPTY_SETTINGS so the form
 * always has every one of the 96 fields; defaults are neutral form values,
 * never fake server state. The server is the source of truth — localStorage
 * is an offline cache at most.
 */
import type { SettingsV1View } from "../api/types";
import type { SystemSettings } from "../types";
import { type Unavailable } from "./absent";

export const EMPTY_SETTINGS: SystemSettings = {
  autonomyLevel: "SUPERVISED",
  defaultExecutionMode: "PAPER",
  multiSigThresholdUsd: 0,
  require2FAForRebalance: false,
  emergencyHaltDrawdownPct: 3,
  autoDeescalateOnAnomaly: false,
  warningDrawdownPct: 1,
  deriskDrawdownPct: 2,
  maxPositionConcentrationPct: 15,
  maxClassExposurePct: 40,
  maxGrossLeverage: 1,
  maxCorrelationCap: 0,
  overnightDerisking: false,
  var95DailyLimitUsd: 0,
  minConsensusThresholdPct: 75,
  maxDebateRounds: 3,
  mandatoryChallengerGate: false,
  dynamicReputationWeighting: false,
  agentLearningRate: 0,
  macroAgentBaseWeight: 0,
  quantAgentBaseWeight: 0,
  sentimentAgentBaseWeight: 0,
  riskSentinelBaseWeight: 0,
  defaultAlgorithm: "TWAP",
  maxSlippageBps: 2,
  twapWindowMinutes: 15,
  preTradeLatencyTimeoutMs: 0,
  enableDarkPoolCrossing: false,
  venues: [],
  taxLotMethod: "HIFO",
  capGainsProvisionRatePct: 0,
  dailyControllerSignOffRequired: false,
  washSaleGuard: false,
  autoTaxLossHarvesting: false,
  taxLossHarvestMinLossUsd: 0,
  baseReportingCurrency: "USD",
  fiscalYearEnd: "",
  tradingWindowMode: "24_7_GLOBAL",
  rebalanceCooldownMinutes: 0,
  expectedShortfallCapPct: 0,
  maxSectorBetaCap: 0,
  macroAgentModel: "",
  quantAgentModel: "",
  sentimentAgentModel: "",
  riskSentinelModel: "",
  inferenceTemperature: 0,
  promptSanitizerActive: false,
  oracleProvider: "CHAINLINK_PYTH_DUAL",
  oracleStalenessMaxSec: 0,
  maxOracleDeviationBps: 0,
  gasMaxGweiCap: 0,
  flashbotsMevProtection: false,
  backtestLookbackYears: 1,
  monteCarloSimulationsCount: 0,
  stressTestScenario: "COVID_CRASH_2020",
  hardwareKeyFido2Required: false,
  sessionIdleTimeoutMinutes: 0,
  killSwitchRequirePin: false,
  alertOnDrawdownWarning: false,
  alertOnDrawdownDerisk: false,
  alertOnLargeFills: false,
  alertOnDebateDeadlock: false,
  alertOnMerkleBlock: false,
  acousticAlerts: "MUTED",
  webhookUrl: "",
  telegramAlertsEnabled: false,
  telegramChatIdMasked: "",
  pagerDutyIntegration: false,
  // No accentTheme: appearance is client-local (see `lib/theme.ts`). The server never
  // defined the field, so carrying it here only put an unknown key in every settings PUT.
  refreshRateMs: 0,
  marketClockTimezone: "UTC",
  privacyBalanceMask: false,
  tradingViewApiEnabled: false,
  tradingViewApiKey: "",
  tradingViewClientId: "",
  tradingViewDatafeedUrl: "",
  tradingViewDefaultTheme: "dark",
  tradingViewInterval: "15",
  tradingViewChartType: "CANDLES",
  tradingViewWebhooksEnabled: false,
  tradingViewWebhookSecret: "",
  tradingViewShowVolume: true,
  tradingViewShowIndicators: true,
  tradingViewActiveIndicators: [],
  tradingViewSymbolMapping: {},
};

export interface AdaptedSettings {
  version: number;
  settings: SystemSettings;
}

type RawView = SettingsV1View & { payload?: Record<string, unknown> };

export function adaptSettingsV1(payload: RawView): AdaptedSettings | Unavailable {
  if (payload.available === false) {
    const reason = payload.reason;
    return {
      unavailable:
        typeof reason === "string" && reason.length > 0 ? reason : "settings unavailable",
    };
  }
  const settingsObj = (payload.settings as Record<string, unknown> | undefined) ?? {};
  const legacyObj = (payload.payload as Record<string, unknown> | undefined) ?? {};
  const blob = { ...legacyObj, ...settingsObj };
  const merged = { ...EMPTY_SETTINGS } as Record<string, unknown>;
  for (const [k, v] of Object.entries(blob)) {
    if (k in merged && v !== undefined) merged[k] = v;
  }
  return { version: payload.version ?? 0, settings: merged as unknown as SystemSettings };
}
