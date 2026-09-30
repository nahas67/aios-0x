/**
 * positionsAdapter: /api/v1/positions rows → zip Position view model.
 *
 * Backend: { execution_id, symbol, action, qty, entry, mark, unrealized,
 *            stop, target, mark_value, asset_class }
 * View:    { id, side, size, entryPrice, markPrice, unrealizedPnlUsd,
 *            unrealizedPnlPct, stopLossPrice, takeProfitPrice, ... }
 */
import type { Position as BackendPosition } from "../api/types";
import type { AssetClass, Position } from "../types";
import { type Unavailable } from "./absent";

const KNOWN_CLASSES: readonly string[] = [
  "GLOBAL_EQUITY",
  "US_EQUITY",
  "POLYMARKET",
  "COMMODITY",
  "FX",
  "CRYPTO",
  "RATES",
  "EQUITY",
];

function toAssetClass(raw: string): AssetClass {
  const up = (raw ?? "").toUpperCase();
  return (KNOWN_CLASSES as readonly string[]).includes(up) ? (up as AssetClass) : "EQUITY";
}

export function adaptPosition(p: BackendPosition): Position {
  const side = p.action === "SELL" ? "SHORT" : "LONG";
  const basis = p.entry * p.qty;
  const unrealizedPnlPct = basis !== 0 ? (p.unrealized / Math.abs(basis)) * 100 : 0;
  return {
    id: p.execution_id,
    symbol: p.symbol,
    name: p.symbol,
    assetClass: toAssetClass(p.asset_class),
    side,
    size: p.qty,
    entryPrice: p.entry,
    markPrice: p.mark,
    notionalUsd: p.mark_value,
    unrealizedPnlUsd: p.unrealized,
    unrealizedPnlPct,
    stopLossPrice: p.stop ?? undefined,
    takeProfitPrice: p.target ?? undefined,
  };
}

export function adaptPositions(
  payload: { positions: BackendPosition[] } | { available: false; reason?: string },
): Position[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "positions unavailable" };
  }
  return payload.positions.map(adaptPosition);
}
