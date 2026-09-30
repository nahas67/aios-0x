/**
 * ordersAdapter: /api/v1/orders rows → zip ExecutionOrder rows.
 * Strategy / agent / venue / slippage have no source in /orders and stay "—"/0.
 */
import type { Order } from "../api/types";
import type { ExecutionOrder } from "../types";
import { type Unavailable } from "./absent";

function toState(status: string): ExecutionOrder["orderState"] {
  const s = (status ?? "").toUpperCase();
  if (s.includes("FILL")) return "FILLED";
  if (s.includes("CANCEL") || s.includes("REJECT")) return "CANCELLED";
  if (s.includes("PARTIAL")) return "PARTIAL";
  if (s.includes("VERIFY")) return "VERIFYING";
  return "ROUTING";
}

export function adaptOrder(o: Order): ExecutionOrder {
  const fillPrice = o.avg_fill_price ?? 0;
  return {
    id: o.client_order_id,
    time: o.created_at,
    symbol: o.symbol,
    side: o.side === "SELL" ? "SELL" : "BUY",
    quantity: o.quantity,
    notionalUsd: o.quantity * fillPrice,
    orderState: toState(o.status),
    fillPrice,
    slippageBps: 0,
    strategy: "—",
    agent: "—",
    riskState: "COMPLIANT",
    venue: "—",
  };
}

export function adaptOrders(
  payload: { orders: Order[] } | { available: false; reason?: string },
): ExecutionOrder[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "orders unavailable" };
  }
  return payload.orders.map(adaptOrder);
}
