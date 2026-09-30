/**
 * marketAdapter: /api/v1/market/candles → chart bars + nullable indicators.
 *
 * Backend: {available:true, symbol, tf, candles:[{time,open,high,low,close,
 *            volume}], indicators:{ema20,ema50,rsi14,macd,bollinger}, source}
 *          or {available:false, reason}.
 * Indicators are null when the real series is too short — the chart renders
 * "—" for those, never a client-computed substitute.
 */
import type { MarketCandles, MarketCandle, MarketIndicators } from "../api/types";
import { type Unavailable } from "./absent";

export interface ChartBar extends MarketCandle {
  timestamp: number;
}

export interface AdaptedMarket {
  symbol: string;
  tf: string;
  bars: ChartBar[];
  indicators: MarketIndicators;
  source: string | null;
}

export function adaptMarketCandles(payload: MarketCandles): AdaptedMarket | Unavailable {
  if (payload.available === false) {
    const reason = payload.reason;
    return {
      unavailable: typeof reason === "string" && reason.length > 0 ? reason : "market feed unavailable",
    };
  }
  return {
    symbol: payload.symbol,
    tf: payload.tf,
    bars: payload.candles.map((c) => ({
      ...c,
      timestamp: Date.parse(c.time) || 0,
    })),
    indicators: payload.indicators,
    source: payload.source ?? null,
  };
}
