import React, { useState } from 'react';
import { ExecutionOrder } from '../types';
import { Zap } from 'lucide-react';

interface LiveExecutionTapeProps {
  orders: ExecutionOrder[];
  onSelectOrder?: (order: ExecutionOrder) => void;
  className?: string;
}

export const LiveExecutionTape: React.FC<LiveExecutionTapeProps> = ({
  orders,
  onSelectOrder,
  className = '',
}) => {
  const [filterSide, setFilterSide] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');

  const filteredOrders = filterSide === 'ALL'
    ? orders
    : orders.filter(o => o.side === filterSide);

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            LIVE EXECUTION TAPE & ORDER ROUTER
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
            TWAP / VWAP SLICER
          </span>
        </div>

        {/* Side Filter */}
        <div className="flex items-center gap-1 bg-surface-sunken p-0.5 rounded border border-border-subtle text-[10px] font-mono">
          {(['ALL', 'BUY', 'SELL'] as const).map(side => (
            <button
              key={side}
              onClick={() => setFilterSide(side)}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterSide === side
                  ? 'bg-info-bg text-accent font-bold border border-accent'
                  : 'text-text-muted hover:text-text-strong'
              }`}
            >
              {side}
            </button>
          ))}
        </div>
      </div>

      {/* Dense Institutional Execution Table */}
      <div className="overflow-x-auto my-2 max-h-[300px] overflow-y-auto">
        <table className="w-full text-left font-mono text-[11px] border-collapse">
          <thead>
            <tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
              <th className="py-1.5 px-2">TIME</th>
              <th className="py-1.5 px-2">SYMBOL</th>
              <th className="py-1.5 px-2">SIDE</th>
              <th className="py-1.5 px-2 text-right">QUANTITY</th>
              <th className="py-1.5 px-2 text-right">FILL PRICE</th>
              <th className="py-1.5 px-2 text-right">SLIPPAGE</th>
              <th className="py-1.5 px-2">STRATEGY</th>
              <th className="py-1.5 px-2">AGENT</th>
              <th className="py-1.5 px-2 text-center">RISK STATE</th>
              <th className="py-1.5 px-2 text-right">VENUE</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-veil">
            {filteredOrders.map((order) => {
              const isBuy = order.side === 'BUY';
              return (
                <tr
                  key={order.id}
                  onClick={() => onSelectOrder && onSelectOrder(order)}
                  className="hover:bg-info-bg cursor-pointer transition-colors group"
                >
                  <td className="py-1.5 px-2 text-text-muted">{order.time}</td>
                  <td className="py-1.5 px-2 font-bold text-text-strong group-hover:text-accent">
                    {order.symbol}
                  </td>
                  <td className="py-1.5 px-2">
                    <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                      isBuy ? 'text-positive bg-positive-bg border border-positive' : 'text-destructive bg-destructive-bg border border-destructive'
                    }`}>
                      {order.side}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-strong font-mono-num">
                    {order.quantity.toLocaleString()}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-strong font-mono-num font-medium">
                    ${order.fillPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono-num text-text-muted">
                    {order.slippageBps} bps
                  </td>
                  <td className="py-1.5 px-2 text-text truncate max-w-[110px]">
                    {order.strategy}
                  </td>
                  <td className="py-1.5 px-2 text-text-muted truncate max-w-[100px]">
                    {order.agent}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    <span className="text-[9px] px-1 rounded bg-positive-bg text-positive border border-positive">
                      {order.riskState}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-subtle text-[10px]">
                    {order.venue}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer Tape Stats */}
      <div className="pt-2 border-t border-border-subtle text-[10px] font-mono text-text-subtle flex items-center justify-between">
        <span>{orders.length} ORDERS • SOURCE: /api/v1/orders</span>
        <span className="text-text-muted">SLIPPAGE: NOT REPORTED BY BACKEND</span>
      </div>
    </div>
  );
};
