import React, { useState, useEffect } from 'react';
import { Activity } from 'lucide-react';

interface TradeTapeProps {
  symbol: string;
  markPrice: number;
}

interface TradeTapeItem {
  id: string;
  time: string;
  price: number;
  size: number;
  side: 'BUY' | 'SELL';
  venue: string;
  isWhale?: boolean;
}

export const TradeTapeTimeSales: React.FC<TradeTapeProps> = ({
  symbol,
  markPrice,
}) => {
  const [trades, setTrades] = useState<TradeTapeItem[]>([]);

  // Initialize trade prints
  useEffect(() => {
    const isCrypto = symbol.includes('BTC') || symbol.includes('ETH');
    const isPoly = symbol.startsWith('PM-');
    const venues = ['Binance FIX', 'Coinbase Prime', 'CME Aurora', 'IEX Direct', 'Polymarket CLOB', 'TSE Tokyo'];

    const initial: TradeTapeItem[] = [];
    const now = Date.now();

    for (let i = 0; i < 15; i++) {
      const time = new Date(now - i * 1400).toTimeString().substring(0, 8);
      const side: 'BUY' | 'SELL' = Math.random() > 0.48 ? 'BUY' : 'SELL';
      const offset = (Math.random() - 0.5) * (markPrice * 0.001);
      const price = +(markPrice + offset).toFixed(symbol.includes('JPY') ? 1 : isPoly ? 4 : 2);
      const size = Math.floor(Math.random() * (isCrypto ? 8 : isPoly ? 15000 : 800)) + (isCrypto ? 1 : 25);
      const isWhale = size * price > 50000;

      initial.push({
        id: `trd-${i}-${Date.now()}`,
        time,
        price,
        size,
        side,
        venue: venues[Math.floor(Math.random() * venues.length)],
        isWhale
      });
    }

    setTrades(initial);
  }, [symbol, markPrice]);

  // Live real-time incoming execution stream
  useEffect(() => {
    const isCrypto = symbol.includes('BTC') || symbol.includes('ETH');
    const isPoly = symbol.startsWith('PM-');
    const venues = ['Binance FIX', 'Coinbase Prime', 'CME Aurora', 'IEX Direct', 'Polymarket CLOB', 'TSE Tokyo'];

    const interval = setInterval(() => {
      const time = new Date().toTimeString().substring(0, 8);
      const side: 'BUY' | 'SELL' = Math.random() > 0.47 ? 'BUY' : 'SELL';
      const offset = (Math.random() - 0.5) * (markPrice * 0.0008);
      const price = +(markPrice + offset).toFixed(symbol.includes('JPY') ? 1 : isPoly ? 4 : 2);
      const size = Math.floor(Math.random() * (isCrypto ? 10 : isPoly ? 20000 : 1200)) + (isCrypto ? 1 : 50);
      const isWhale = size * price > 45000;

      const newTrade: TradeTapeItem = {
        id: `trd-live-${Date.now()}`,
        time,
        price,
        size,
        side,
        venue: venues[Math.floor(Math.random() * venues.length)],
        isWhale
      };

      setTrades(prev => [newTrade, ...prev.slice(0, 24)]);
    }, 1400);

    return () => clearInterval(interval);
  }, [symbol, markPrice]);

  return (
    <div className="bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          <span className="font-bold text-slate-100 text-[11px] uppercase tracking-wider">Time & Sales Tape</span>
        </div>
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/50">
          STREAMING
        </span>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-4 px-3 py-1.5 text-[9px] font-bold text-slate-400 border-b border-white/[0.04] uppercase">
        <div>Time</div>
        <div className="text-right">Price</div>
        <div className="text-right">Size</div>
        <div className="text-right">Venue</div>
      </div>

      {/* Trade Stream */}
      <div className="divide-y divide-white/[0.02] max-h-[220px] overflow-y-auto">
        {trades.map((trd) => (
          <div
            key={trd.id}
            className={`grid grid-cols-4 px-3 py-1 text-[10px] items-center transition-colors ${
              trd.isWhale ? 'bg-amber-950/20 font-bold' : 'hover:bg-white/[0.02]'
            }`}
          >
            <div className="text-slate-400 font-mono-num text-[9px] flex items-center gap-1">
              {trd.time}
              {trd.isWhale && <span className="text-amber-400 text-[8px]" title="Whale Institutional Fill">🐋</span>}
            </div>

            <div className={`text-right font-mono-num font-bold ${
              trd.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {trd.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>

            <div className="text-right text-slate-300 font-mono-num">
              {trd.size.toLocaleString()}
            </div>

            <div className="text-right text-slate-400 text-[9px] truncate pl-1">
              {trd.venue.split(' ')[0]}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
