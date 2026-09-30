import React, { useState, useEffect } from 'react';
import { Layers } from 'lucide-react';

interface OrderBookProps {
  symbol: string;
  markPrice: number;
  onSelectPrice?: (price: number) => void;
}

interface OrderBookLevel {
  price: number;
  size: number;
  total: number;
}

export const OrderBookDOM: React.FC<OrderBookProps> = ({
  symbol,
  markPrice,
  onSelectPrice,
}) => {
  const [precision] = useState<number>(symbol.includes('JPY') || symbol.includes('7203') ? 1 : symbol.startsWith('PM-') ? 4 : 2);
  const [depthRows] = useState<number>(7);
  const [bids, setBids] = useState<OrderBookLevel[]>([]);
  const [asks, setAsks] = useState<OrderBookLevel[]>([]);
  const [spreadBps, setSpreadBps] = useState<number>(0.8);
  const [lastTickSide, setLastTickSide] = useState<'BUY' | 'SELL' | null>(null);

  // Generate initial order book around mark price
  useEffect(() => {
    const isCrypto = symbol.includes('BTC') || symbol.includes('ETH');
    const isPoly = symbol.startsWith('PM-');
    const step = isPoly ? 0.005 : isCrypto ? 2.5 : markPrice * 0.0004;

    const newAsks: OrderBookLevel[] = [];
    let askTotal = 0;
    for (let i = depthRows; i >= 1; i--) {
      const price = +(markPrice + i * step).toFixed(precision);
      const size = Math.floor(Math.random() * (isCrypto ? 12 : isPoly ? 24000 : 1500)) + (isCrypto ? 1 : 100);
      askTotal += size;
      newAsks.push({ price, size, total: askTotal });
    }

    const newBids: OrderBookLevel[] = [];
    let bidTotal = 0;
    for (let i = 1; i <= depthRows; i++) {
      const price = +(markPrice - i * step).toFixed(precision);
      const size = Math.floor(Math.random() * (isCrypto ? 12 : isPoly ? 24000 : 1500)) + (isCrypto ? 1 : 100);
      bidTotal += size;
      newBids.push({ price, size, total: bidTotal });
    }

    setAsks(newAsks);
    setBids(newBids);
  }, [symbol, markPrice, depthRows, precision]);

  // Micro-tick animation for dynamic depth
  useEffect(() => {
    const interval = setInterval(() => {
      const isAsk = Math.random() > 0.5;
      setLastTickSide(isAsk ? 'SELL' : 'BUY');

      if (isAsk) {
        setAsks(prev => {
          if (prev.length === 0) return prev;
          const idx = Math.floor(Math.random() * prev.length);
          const next = [...prev];
          const delta = (Math.random() - 0.45) * 50;
          next[idx] = { ...next[idx], size: Math.max(10, Math.round(next[idx].size + delta)) };
          return next;
        });
      } else {
        setBids(prev => {
          if (prev.length === 0) return prev;
          const idx = Math.floor(Math.random() * prev.length);
          const next = [...prev];
          const delta = (Math.random() - 0.45) * 50;
          next[idx] = { ...next[idx], size: Math.max(10, Math.round(next[idx].size + delta)) };
          return next;
        });
      }

      setSpreadBps(+(0.4 + Math.random() * 0.8).toFixed(2));
    }, 800);

    return () => clearInterval(interval);
  }, []);

  const maxAskTotal = asks[0]?.total || 1;
  const maxBidTotal = bids[bids.length - 1]?.total || 1;
  const maxTotal = Math.max(maxAskTotal, maxBidTotal, 1);

  return (
    <div className="bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-100 text-[11px] uppercase tracking-wider">L2 Order Book</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06]">
            DOM
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span className="text-slate-400">Spread:</span>
          <span className="text-cyan-300 font-bold font-mono-num">{spreadBps} bps</span>
        </div>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-3 px-3 py-1.5 text-[9px] font-bold text-slate-400 border-b border-white/[0.04] uppercase">
        <div>Price (USD)</div>
        <div className="text-right">Size</div>
        <div className="text-right">Total</div>
      </div>

      {/* ASKS (Sells / Red) */}
      <div className="flex flex-col-reverse py-1">
        {asks.map((level, i) => {
          const depthPct = Math.min(100, (level.total / maxTotal) * 100);
          return (
            <div
              key={`ask-${i}`}
              onClick={() => onSelectPrice && onSelectPrice(level.price)}
              className="grid grid-cols-3 px-3 py-0.5 text-[10px] hover:bg-white/[0.04] cursor-pointer relative group transition-colors"
            >
              {/* Depth background fill */}
              <div 
                className="absolute top-0 bottom-0 right-0 bg-rose-500/15 pointer-events-none transition-all duration-300"
                style={{ width: `${depthPct}%` }}
              />
              <div className="text-rose-400 font-bold relative z-10 font-mono-num">{level.price.toFixed(precision)}</div>
              <div className="text-right text-slate-300 relative z-10 font-mono-num">{level.size.toLocaleString()}</div>
              <div className="text-right text-slate-400 relative z-10 font-mono-num">{level.total.toLocaleString()}</div>
            </div>
          );
        })}
      </div>

      {/* CURRENT MID / MARK PRICE STRIP */}
      <div className="my-0.5 px-3 py-1.5 bg-[#0e1017] border-y border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold font-mono-num ${
            lastTickSide === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            {markPrice.toFixed(precision)}
          </span>
          <span className="text-[9px] text-slate-400 uppercase">Mark</span>
        </div>

        <div className="flex items-center gap-1.5 text-[9px] text-slate-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
          <span className="text-slate-300 font-mono">1.2ms FIX</span>
        </div>
      </div>

      {/* BIDS (Buys / Green) */}
      <div className="flex flex-col py-1">
        {bids.map((level, i) => {
          const depthPct = Math.min(100, (level.total / maxTotal) * 100);
          return (
            <div
              key={`bid-${i}`}
              onClick={() => onSelectPrice && onSelectPrice(level.price)}
              className="grid grid-cols-3 px-3 py-0.5 text-[10px] hover:bg-white/[0.04] cursor-pointer relative group transition-colors"
            >
              {/* Depth background fill */}
              <div 
                className="absolute top-0 bottom-0 right-0 bg-emerald-500/15 pointer-events-none transition-all duration-300"
                style={{ width: `${depthPct}%` }}
              />
              <div className="text-emerald-400 font-bold relative z-10 font-mono-num">{level.price.toFixed(precision)}</div>
              <div className="text-right text-slate-300 relative z-10 font-mono-num">{level.size.toLocaleString()}</div>
              <div className="text-right text-slate-400 relative z-10 font-mono-num">{level.total.toLocaleString()}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
