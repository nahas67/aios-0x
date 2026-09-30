/**
 * regimesAdapter: /api/v1/regimes → zip MarketRegimeItem rows.
 *
 * The backend labels trend (UP/DOWN/FLAT) and vol regime only. Prices,
 * 24h change, sparklines, confidence, and the polymarket/fx/commodity
 * sub-blocks have no source and are dropped — never synthesized.
 */
import type { Regime } from "../api/types";
import type { MarketRegimeItem } from "../types";
import { type Unavailable } from "./absent";

function toTrend(raw: string): MarketRegimeItem["trend"] {
  const t = (raw ?? "").toUpperCase();
  if (t.includes("STRONG") && t.includes("BULL")) return "STRONG_BULL";
  if (t.includes("STRONG") && t.includes("BEAR")) return "STRONG_BEAR";
  if (t.includes("BULL") || t === "UP") return "BULL";
  if (t.includes("BEAR") || t === "DOWN") return "BEAR";
  return "SIDEWAYS";
}

function toVolatility(raw: string): MarketRegimeItem["volatility"] {
  const v = (raw ?? "").toUpperCase();
  if (v.includes("EXTREME")) return "EXTREME";
  if (v.includes("HIGH")) return "HIGH";
  if (v.includes("LOW")) return "LOW";
  return "NORMAL";
}

export function adaptRegimes(
  payload: { regimes: Regime[] } | { available: false; reason?: string },
): MarketRegimeItem[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "regimes unavailable" };
  }
  return payload.regimes.map((r) => ({
    symbol: r.symbol,
    name: r.symbol,
    category: "MACRO",
    // No price feed behind /regimes: 0 renders as "—" in MarketRegimeField.
    price: 0,
    change24hPct: 0,
    trend: toTrend(r.trend),
    volatility: toVolatility(r.vol_regime),
    momentum: 0,
    regime: `${r.trend} / ${r.vol_regime} vol`,
    confidencePct: 0,
    sparkline: [],
  }));
}
