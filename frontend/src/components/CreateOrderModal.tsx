import React, { useState } from 'react';
import {
  Zap,
  X,
  ShieldCheck,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';

interface CreateOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNotice: (msg: string) => void;
}

/**
 * Order staging modal. The backend exposes no order-submission endpoint
 * (orders are read-only over HTTP), so this form stages parameters for
 * review only: submitting reports that nothing was sent instead of
 * fabricating an order id, fill price, or slippage figure.
 */
export const CreateOrderModal: React.FC<CreateOrderModalProps> = ({
  isOpen,
  onClose,
  onNotice,
}) => {
  const [symbol, setSymbol] = useState<string>('BTC/USD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [orderType, setOrderType] = useState<'TWAP' | 'VWAP' | 'POV' | 'ICEBERG' | 'MARKET'>('TWAP');
  const [amount, setAmount] = useState<string>('12.5');
  const [price, setPrice] = useState<string>('64200.00');
  const [durationMinutes, setDurationMinutes] = useState<number>(30);
  const [venue, setVenue] = useState<string>('AUTO_SOR');
  const [maxSlippageBps, setMaxSlippageBps] = useState<number>(1.5);
  const [slicesCount, setSlicesCount] = useState<number>(12);

  if (!isOpen) return null;

  const totalNotional = (parseFloat(amount) || 0) * (parseFloat(price) || 0);

  const handleDispatch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) return;
    onNotice(
      `Order NOT sent: no order-submission endpoint exists server-side. ` +
      `Staged ${side} ${amount} ${symbol} (${orderType}, ${slicesCount} slices over ${durationMinutes}m, ` +
      `slippage cap ${maxSlippageBps} bps, venue ${venue}) was discarded, no fill fabricated.`,
    );
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-sunken backdrop-blur-sm animate-fade-in font-mono">
      <div className="bg-[var(--color-surface-1)] border border-accent rounded-md w-full max-w-xl shadow-[0_0_50px_rgba(0,240,255,0.2)] overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-border-strong flex items-center justify-between bg-surface-sunken">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-accent" />
            <div>
              <h3 className="text-sm font-bold text-text-strong uppercase tracking-wider">
                INSTITUTIONAL ALGORITHMIC ORDER STAGING
              </h3>
              <p className="text-[10px] text-text-muted">
                Parameter review only — submission is not wired
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-text-muted hover:text-text-strong hover:bg-surface-raised transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleDispatch} className="p-5 space-y-4 text-xs">
          {/* Not-wired notice */}
          <div className="rounded border border-warning bg-warning-bg px-3 py-2 text-[11px] leading-relaxed text-warning">
            Order routing is not wired: the backend publishes orders read-only. Submitting
            this form stages parameters for review and reports honestly — no order id,
            fill, or slippage is generated.
          </div>

          {/* Asset & Direction Selection */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Target Instrument
              </label>
              <select
                value={symbol}
                onChange={(e) => {
                  setSymbol(e.target.value);
                  if (e.target.value.includes('BTC')) setPrice('64200.00');
                  else if (e.target.value.includes('ETH')) setPrice('3450.00');
                  else if (e.target.value.includes('NVDA')) setPrice('128.50');
                  else if (e.target.value.includes('SOL')) setPrice('148.20');
                  else if (e.target.value.includes('SPY')) setPrice('562.10');
                  else if (e.target.value.includes('AAPL')) setPrice('228.40');
                }}
                className="w-full bg-surface-deep border border-border-strong rounded px-3 py-2 text-text-strong font-mono focus:border-accent focus:outline-none"
              >
                <option value="BTC/USD">BTC/USD (Bitcoin Spot)</option>
                <option value="ETH/USD">ETH/USD (Ethereum Spot)</option>
                <option value="SOL/USD">SOL/USD (Solana Spot)</option>
                <option value="NVDA">NVDA (NVIDIA Corporation)</option>
                <option value="SPY">SPY (S&amp;P 500 ETF Trust)</option>
                <option value="AAPL">AAPL (Apple Inc.)</option>
                <option value="BTC-PERP">BTC-PERP (Hyperliquid L1)</option>
                <option value="ETH-PERP">ETH-PERP (Hyperliquid L1)</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Execution Side
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSide('BUY')}
                  className={`py-2 rounded font-bold transition-all flex items-center justify-center gap-1.5 border ${
                    side === 'BUY'
                      ? 'bg-positive-bg border-positive text-positive shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                      : 'bg-surface-sunken border-border-strong text-text-muted hover:text-text-strong'
                  }`}
                >
                  <ArrowUpRight className="w-3.5 h-3.5" />
                  BUY / LONG
                </button>
                <button
                  type="button"
                  onClick={() => setSide('SELL')}
                  className={`py-2 rounded font-bold transition-all flex items-center justify-center gap-1.5 border ${
                    side === 'SELL'
                      ? 'bg-destructive-bg border-destructive text-destructive shadow-[0_0_12px_rgba(244,63,94,0.3)]'
                      : 'bg-surface-sunken border-border-strong text-text-muted hover:text-text-strong'
                  }`}
                >
                  <ArrowDownRight className="w-3.5 h-3.5" />
                  SELL / SHORT
                </button>
              </div>
            </div>
          </div>

          {/* Size & Reference Price */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Order Quantity
              </label>
              <div className="relative">
                <input
                  type="number"
                  step="any"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full bg-surface-deep border border-border-strong rounded px-3 py-2 text-text-strong font-mono focus:border-accent focus:outline-none"
                  placeholder="0.00"
                  required
                />
                <span className="absolute right-3 top-2 text-[10px] text-text-subtle font-mono">
                  {symbol.split('/')[0].split('-')[0]}
                </span>
              </div>
            </div>

            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Benchmark / Limit Price ($)
              </label>
              <input
                type="number"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="w-full bg-surface-deep border border-border-strong rounded px-3 py-2 text-text-strong font-mono focus:border-accent focus:outline-none"
                placeholder="0.00"
                required
              />
            </div>
          </div>

          {/* Slicing Algorithm & Venue Routing */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Algorithmic Slicer
              </label>
              <select
                value={orderType}
                onChange={(e) => setOrderType(e.target.value as never)}
                className="w-full bg-surface-deep border border-border-strong rounded px-3 py-2 text-text-strong font-mono focus:border-accent focus:outline-none"
              >
                <option value="TWAP">TWAP (Time-Weighted Average Price)</option>
                <option value="VWAP">VWAP (Volume-Weighted Average Price)</option>
                <option value="POV">POV (Percentage of Volume - 12%)</option>
                <option value="ICEBERG">Iceberg (Hidden Display Slices)</option>
                <option value="MARKET">Direct Market Immediate</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] text-text-muted uppercase tracking-wider mb-1 block">
                Venue Routing Gateway
              </label>
              <select
                value={venue}
                onChange={(e) => setVenue(e.target.value)}
                className="w-full bg-surface-deep border border-border-strong rounded px-3 py-2 text-text-strong font-mono focus:border-accent focus:outline-none"
              >
                <option value="AUTO_SOR">Auto Smart Order Routing (Lowest Cost)</option>
                <option value="Binance Institutional">Binance Institutional FIX 4.4</option>
                <option value="CME Group Direct">CME Group Direct iLink3</option>
                <option value="Hyperliquid Perps">Hyperliquid L1 Low Latency</option>
                <option value="Coinbase Prime">Coinbase Prime OTC</option>
                <option value="Interactive Brokers">Interactive Brokers TWS Gateway</option>
              </select>
            </div>
          </div>

          {/* Slicing Fine-Tuning */}
          {orderType !== 'MARKET' && (
            <div className="p-3 rounded bg-surface-veil border border-border-subtle grid grid-cols-3 gap-3">
              <div>
                <label className="text-[10px] text-text-muted block mb-1">Duration Window</label>
                <select
                  value={durationMinutes}
                  onChange={(e) => setDurationMinutes(Number(e.target.value))}
                  className="w-full bg-surface-deep border border-border-strong rounded px-2 py-1 text-xs text-text-strong font-mono"
                >
                  <option value={5}>5 Minutes</option>
                  <option value={15}>15 Minutes</option>
                  <option value={30}>30 Minutes</option>
                  <option value={60}>1 Hour</option>
                  <option value={240}>4 Hours</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-text-muted block mb-1">Micro Slices</label>
                <select
                  value={slicesCount}
                  onChange={(e) => setSlicesCount(Number(e.target.value))}
                  className="w-full bg-surface-deep border border-border-strong rounded px-2 py-1 text-xs text-text-strong font-mono"
                >
                  <option value={6}>6 Slices</option>
                  <option value={12}>12 Slices</option>
                  <option value={24}>24 Slices</option>
                  <option value={60}>60 Slices</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-text-muted block mb-1">Max Slippage Cap</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.1"
                    value={maxSlippageBps}
                    onChange={(e) => setMaxSlippageBps(Number(e.target.value))}
                    className="w-full bg-surface-deep border border-border-strong rounded px-2 py-1 text-xs text-text-strong font-mono"
                  />
                  <span className="text-[10px] text-text-subtle">BPS</span>
                </div>
              </div>
            </div>
          )}

          {/* Staged calculation */}
          <div className="p-3 rounded bg-surface-sunken border border-border-strong space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-muted">STAGED NOTIONAL:</span>
              <span className="text-text-strong font-bold font-mono">
                ${totalNotional.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px] pt-1 border-t border-border-subtle">
              <span className="text-text-subtle flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" />
                Pre-trade firewall: not evaluated client-side
              </span>
              <span className="text-text-subtle text-[10px]">
                NOT SENT
              </span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded bg-surface-veil hover:bg-surface-raised text-text transition-colors"
            >
              CANCEL
            </button>
            <button
              type="submit"
              disabled={!amount || parseFloat(amount) <= 0}
              className="px-5 py-2 rounded font-bold flex items-center gap-2 transition-all bg-surface-raised hover:bg-surface-overlay border border-border-strong text-text-strong"
            >
              <Zap className="w-4 h-4" />
              <span>STAGE {side} ORDER (NOT SENT)</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
