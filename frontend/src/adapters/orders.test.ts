import { describe, expect, it } from "vitest";
import { adaptOrders } from "./orders";
import type { Order } from "../api/types";

const order: Order = {
  client_order_id: "c-1",
  symbol: "BTC/USD",
  side: "BUY",
  status: "FILLED",
  quantity: 2,
  avg_fill_price: 65000,
  reject_reason: null,
  created_at: "2026-09-30T10:00:00Z",
};

describe("ordersAdapter", () => {
  it("maps backend orders to ExecutionOrder rows", () => {
    const out = adaptOrders({ orders: [order] });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out[0]).toMatchObject({
      id: "c-1",
      symbol: "BTC/USD",
      side: "BUY",
      quantity: 2,
      orderState: "FILLED",
      fillPrice: 65000,
      notionalUsd: 130000,
    });
  });

  it("maps rejected orders to CANCELLED", () => {
    const out = adaptOrders({
      orders: [{ ...order, client_order_id: "c-2", status: "REJECTED" }],
    });
    if ("unavailable" in out) throw new Error("unexpected unavailable");
    expect(out[0].orderState).toBe("CANCELLED");
  });

  it("branches on {available:false}", () => {
    expect(adaptOrders({ available: false, reason: "z" })).toEqual({ unavailable: "z" });
  });
});
