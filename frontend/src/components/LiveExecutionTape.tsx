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
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            LIVE EXECUTION TAPE & ORDER ROUTER
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
            TWAP / VWAP SLICER
          </span>
        </div>

        {/* Side Filter */}
        <div className="flex items-center gap-1 bg-black/40 p-0.5 rounded border border-white/[0.06] text-[10px] font-mono">
          {(['ALL', 'BUY', 'SELL'] as const).map(side => (
            <button
              key={side}
              onClick={() => setFilterSide(side)}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterSide === side
                  ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/60'
                  : 'text-slate-400 hover:text-slate-200'
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
            <tr className="border-b border-white/[0.06] text-slate-500 text-[9px] uppercase tracking-wider">
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
          <tbody className="divide-y divide-white/[0.03]">
            {filteredOrders.map((order) => {
              const isBuy = order.side === 'BUY';
              return (
                <tr
                  key={order.id}
                  onClick={() => onSelectOrder && onSelectOrder(order)}
                  className="hover:bg-cyan-950/20 cursor-pointer transition-colors group"
                >
                  <td className="py-1.5 px-2 text-slate-400">{order.time}</td>
                  <td className="py-1.5 px-2 font-bold text-white group-hover:text-cyan-300">
                    {order.symbol}
                  </td>
                  <td className="py-1.5 px-2">
                    <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                      isBuy ? 'text-emerald-400 bg-emerald-950/40 border border-emerald-800/40' : 'text-rose-400 bg-rose-950/40 border border-rose-800/40'
                    }`}>
                      {order.side}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-slate-200 font-mono-num">
                    {order.quantity.toLocaleString()}
                  </td>
                  <td className="py-1.5 px-2 text-right text-white font-mono-num font-medium">
                    ${order.fillPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono-num text-slate-400">
                    {order.slippageBps} bps
                  </td>
                  <td className="py-1.5 px-2 text-slate-300 truncate max-w-[110px]">
                    {order.strategy}
                  </td>
                  <td className="py-1.5 px-2 text-slate-400 truncate max-w-[100px]">
                    {order.agent}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    <span className="text-[9px] px-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">
                      {order.riskState}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-slate-500 text-[10px]">
                    {order.venue}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer Tape Stats */}
      <div className="pt-2 border-t border-white/[0.06] text-[10px] font-mono text-slate-500 flex items-center justify-between">
        <span>AVG INTRADAY SLIPPAGE: <strong className="text-cyan-300">0.78 bps</strong> (BENCHMARK &lt; 2.5 bps)</span>
        <span className="text-emerald-400">STATUS: ZERO REJECTIONS</span>
      </div>
    </div>
  );
};
