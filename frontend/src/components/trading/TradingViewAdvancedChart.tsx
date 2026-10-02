import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  BarChart2,
  Layers,
  Maximize2,
  Minimize2,
  Activity,
  RefreshCw,
} from 'lucide-react';
import { Position, SystemSettings } from '../../types';
import { marketApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptMarketCandles, type ChartBar } from '../../adapters/market';
import { Unavailable } from '../Unavailable';

export interface CandleData extends ChartBar {
  ema20?: number;
  ema50?: number;
  ema200?: number;
  bbUpper?: number;
  bbLower?: number;
  bbMiddle?: number;
  rsi?: number;
  macd?: number;
  macdSignal?: number;
  macdHist?: number;
  vwap?: number;
}

interface TradingViewAdvancedChartProps {
  symbol: string;
  name: string;
  category: string;
  settings: SystemSettings;
  activePositions?: Position[];
  onOpenSettings?: () => void;
  onMarkPrice?: (mark: number | null) => void;
}

export type TimeFrame = '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W';
export type ChartStyle = 'CANDLE' | 'HEIKIN' | 'LINE' | 'AREA';

/**
 * Chart data comes from GET /api/v1/market/candles only. The backend returns
 * the latest real OHLCV bar plus server-side indicators (null when the real
 * series is too short — rendered as "—", never computed client-side).
 * Bars accumulate locally per symbol+timeframe so repeated refreshes build a
 * session of real bars; nothing is simulated and there is no tick timer.
 */
export const TradingViewAdvancedChart: React.FC<TradingViewAdvancedChartProps> = ({
  symbol,
  name,
  category,
  settings,
  activePositions = [],
  onOpenSettings,
  onMarkPrice
}) => {
  // Chart Modes: Native SVG vs Official TradingView Pro Widget
  const [chartEngine, setChartEngine] = useState<'NATIVE' | 'TRADINGVIEW'>('NATIVE');
  const [timeframe, setTimeframe] = useState<TimeFrame>('15m');
  const [chartStyle, setChartStyle] = useState<ChartStyle>('CANDLE');

  // Interactive Tools
  const [hoveredCandle, setHoveredCandle] = useState<ChartBar | null>(null);
  const [mouseCoords, setMouseCoords] = useState<{ x: number; y: number; price: number } | null>(null);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [snapshotTaken, setSnapshotTaken] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const candlesQ = useApi(() => marketApi.candles(symbol, timeframe), [symbol, timeframe]);

  // Session cache of real bars, keyed by symbol+timeframe. Refreshes append
  // genuinely new bars (deduped by time); switching keys starts a new cache.
  const cacheKey = `${symbol}|${timeframe}`;
  const [barsByKey, setBarsByKey] = useState<Record<string, ChartBar[]>>({});
  const lastAppendedRef = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!candlesQ.data || candlesQ.data.available === false) return;
    const adapted = adaptMarketCandles(candlesQ.data);
    if ("unavailable" in adapted) return;
    const fresh = adapted.bars.filter((b) => b.time > (lastAppendedRef.current[cacheKey] ?? ""));
    if (fresh.length === 0) return;
    lastAppendedRef.current[cacheKey] = fresh[fresh.length - 1].time;
    setBarsByKey((prev) => {
      const merged = [...(prev[cacheKey] ?? []), ...fresh];
      return { ...prev, [cacheKey]: merged.slice(-120) };
    });
  }, [candlesQ.data, cacheKey]);

  // Reset hover when the feed key changes
  useEffect(() => {
    setHoveredCandle(null);
  }, [cacheKey]);

  const bars = barsByKey[cacheKey] ?? [];

  const adapted =
    candlesQ.data && candlesQ.data.available !== false ? adaptMarketCandles(candlesQ.data) : null;
  const indicators = adapted && !("unavailable" in adapted) ? adapted.indicators : null;
  const feedSource = adapted && !("unavailable" in adapted) ? adapted.source : null;

  // Compute bounding box & scales
  const chartHeight = 480;
  const chartWidth = 840; // responsive SVG viewBox

  const { minPrice, maxPrice, priceRange, maxVolume } = useMemo(() => {
    if (bars.length === 0) return { minPrice: 0, maxPrice: 1, priceRange: 1, minVolume: 0, maxVolume: 100 };

    const min = Math.min(...bars.map(c => c.low));
    const max = Math.max(...bars.map(c => c.high));

    const padding = (max - min) * 0.08 || min * 0.02;
    const maxVol = Math.max(...bars.map(c => c.volume), 100);

    return {
      minPrice: min - padding,
      maxPrice: max + padding,
      priceRange: max - min + padding * 2 || 1,
      minVolume: 0,
      maxVolume: maxVol
    };
  }, [bars]);

  // Price to Y coordinate mapper
  const getY = (val: number) => {
    return chartHeight - ((val - minPrice) / priceRange) * (chartHeight - 40) - 20;
  };

  // Time to X coordinate mapper
  const getX = (index: number) => {
    const candleWidth = (chartWidth - 70) / Math.max(1, bars.length);
    return 10 + index * candleWidth + candleWidth / 2;
  };

  const candleBarWidth = Math.max(2, ((chartWidth - 70) / Math.max(1, bars.length)) * 0.65);

  // Active positions for current symbol
  const symbolPositions = activePositions.filter(p => p.symbol === symbol);

  // TradingView Symbol Translation
  const tvSymbol = settings.tradingViewSymbolMapping?.[symbol] || (
    symbol.includes('/') ? `BINANCE:${symbol.replace('/', '')}` : `NASDAQ:${symbol}`
  );

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || bars.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Scale to viewBox coordinates
    const scaleX = chartWidth / rect.width;
    const scaleY = chartHeight / rect.height;

    const svgX = x * scaleX;
    const svgY = y * scaleY;

    // Calculate price at cursor
    const cursorPrice = maxPrice - (svgY / chartHeight) * priceRange;

    // Find nearest candle
    const candleWidth = (chartWidth - 70) / bars.length;
    const candleIndex = Math.min(bars.length - 1, Math.max(0, Math.floor((svgX - 10) / candleWidth)));

    setHoveredCandle(bars[candleIndex] || null);
    setMouseCoords({ x: svgX, y: svgY, price: Math.max(minPrice, Math.min(maxPrice, cursorPrice)) });
  };

  const handleMouseLeave = () => {
    setHoveredCandle(null);
    setMouseCoords(null);
  };

  const handleTakeSnapshot = () => {
    setSnapshotTaken(true);
    setTimeout(() => setSnapshotTaken(false), 2500);
  };

  const latest = bars[bars.length - 1] ?? null;
  const first = bars[0] ?? null;

  // Report the latest real close upward so the ticket/book share one mark.
  useEffect(() => {
    if (onMarkPrice) onMarkPrice(latest ? latest.close : null);
  }, [latest, onMarkPrice]);
  const sessionChangePct =
    latest && first && first.close !== 0 ? ((latest.close - first.close) / Math.abs(first.close)) * 100 : null;

  const fmtInd = (v: number | null | undefined) =>
    v === null || v === undefined || Number.isNaN(v) ? "—" : String(v);

  return (
    <div
      ref={containerRef}
      className={`bg-[var(--color-surface-0)] border border-border-strong rounded-xl flex flex-col overflow-hidden font-mono select-none transition-all ${
        isFullscreen ? 'fixed inset-4 z-50 shadow-2xl border-accent bg-[var(--color-surface-deep)]' : ''
      }`}
    >
      {/* 1. TOP PRO-CHART HEADER & TICKER BANNER */}
      <div className="bg-[var(--color-surface-2)] border-b border-border-strong px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Left: Asset Ticker Info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-text-strong text-sm tracking-wider">{symbol}</span>
            <span className="text-[10px] text-text-muted font-sans hidden sm:inline max-w-[140px] truncate">
              {name}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-info-bg border border-accent text-[9px] text-accent font-semibold uppercase">
              {category}
            </span>
          </div>

          <div className="h-4 w-px bg-surface-raised" />

          {/* Latest real close + cached-session change (honestly labeled) */}
          <div className="flex items-baseline gap-2">
            <span className="text-base font-bold text-text-strong font-mono-num">
              {latest ? formatPrice(latest.close, symbol) : "—"}
            </span>
            <span className={`flex items-center gap-0.5 text-[11px] font-bold ${
              (sessionChangePct ?? 0) >= 0 ? 'text-positive' : 'text-destructive'
            }`}>
              {sessionChangePct === null ? (
                <span className="text-text-subtle">session: —</span>
              ) : (
                <>{sessionChangePct >= 0 ? '+' : ''}{sessionChangePct.toFixed(2)}% cached</>
              )}
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-4 text-[10px] text-text-muted pl-2 border-l border-border-subtle">
            <div>Session High: <span className="text-text-strong font-mono-num">{latest ? formatPrice(Math.max(...bars.map(b => b.high)), symbol) : "—"}</span></div>
            <div>Session Low: <span className="text-text-strong font-mono-num">{latest ? formatPrice(Math.min(...bars.map(b => b.low)), symbol) : "—"}</span></div>
            <div>Bars: <span className="text-text-strong font-mono-num">{bars.length} real</span></div>
          </div>
        </div>

        {/* Right: Chart Controls & Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Native vs TradingView Pro API Engine Toggle */}
          <div className="bg-surface-deep border border-border-subtle p-0.5 rounded-lg flex items-center gap-0.5">
            <button
              onClick={() => setChartEngine('NATIVE')}
              className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all flex items-center gap-1 ${
                chartEngine === 'NATIVE'
                  ? 'bg-accent text-text-strong shadow-[0_0_10px_rgba(0,240,255,0.3)]'
                  : 'text-text-muted hover:text-text-strong hover:bg-surface-veil'
              }`}
              title="Native SVG engine over the backend candle feed"
            >
              <Activity className="w-3 h-3" />
              Native Feed
            </button>
            <button
              onClick={() => setChartEngine('TRADINGVIEW')}
              className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all flex items-center gap-1 ${
                chartEngine === 'TRADINGVIEW'
                  ? 'bg-violet text-text-strong shadow-[0_0_10px_rgba(99,102,241,0.3)]'
                  : 'text-text-muted hover:text-text-strong hover:bg-surface-veil'
              }`}
              title="Official TradingView Advanced Real-Time Charting Library"
            >
              <BarChart2 className="w-3 h-3" />
              TradingView API Pro
            </button>
          </div>

          {/* Timeframe Selector */}
          <div className="hidden md:flex bg-surface-sunken border border-border-subtle rounded p-0.5 gap-0.5 text-[10px]">
            {(['1m', '5m', '15m', '1h', '4h', '1D', '1W'] as TimeFrame[]).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-0.5 rounded font-medium transition-all ${
                  timeframe === tf
                    ? 'bg-surface-raised text-accent font-bold border border-accent'
                    : 'text-text-muted hover:text-text-strong hover:bg-surface-raised'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Manual feed refresh (no auto tick timer) */}
          <button
            onClick={() => candlesQ.refresh()}
            className="p-1.5 rounded border text-[10px] transition-all flex items-center gap-1 bg-surface-veil text-text border-border-subtle hover:text-text-strong"
            title="Fetch the latest real bar from /api/v1/market/candles"
          >
            <RefreshCw className={`w-3 h-3 ${candlesQ.loading ? 'animate-spin text-accent' : ''}`} />
            <span className="text-[9px] font-bold uppercase">{candlesQ.loading ? 'Fetching' : 'Refresh'}</span>
          </button>

          {/* Screenshot / Snapshot */}
          <button
            onClick={handleTakeSnapshot}
            className="p-1.5 rounded bg-surface-veil border border-border-subtle text-text-muted hover:text-text-strong hover:bg-surface-raised relative"
            title="Capture Chart Snapshot"
          >
            <span className="text-[10px] font-bold px-0.5">PNG</span>
            {snapshotTaken && (
              <span className="absolute -top-7 right-0 bg-info-bg border border-accent text-accent text-[9px] px-1.5 py-0.5 rounded shadow-lg whitespace-nowrap">
                Captured!
              </span>
            )}
          </button>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded bg-surface-veil border border-border-subtle text-text-muted hover:text-text-strong hover:bg-surface-raised"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen Chart'}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. SECONDARY TOOLBAR: STYLE + SERVER INDICATOR READOUTS */}
      {chartEngine === 'NATIVE' && (
        <div className="bg-[var(--color-surface-rail)] border-b border-border-subtle px-3.5 py-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px]">
          {/* Chart Style Switcher */}
          <div className="flex items-center gap-1 text-[10px]">
            <span className="text-text-muted text-[9px] uppercase font-bold mr-1">Style:</span>
            {(['CANDLE', 'HEIKIN', 'LINE', 'AREA'] as ChartStyle[]).map(style => (
              <button
                key={style}
                onClick={() => setChartStyle(style)}
                className={`px-2 py-0.5 rounded transition-all ${
                  chartStyle === style
                    ? 'bg-info-bg text-accent border border-accent font-bold'
                    : 'text-text-muted hover:text-text-strong hover:bg-surface-veil'
                }`}
              >
                {style}
              </button>
            ))}
          </div>

          {/* Server-side indicator readouts (null → "—", never computed here) */}
          <div className="flex items-center gap-3 text-[10px] text-text-muted">
            <span title="Server-computed EMA(20), null when the series is too short">
              EMA20: <strong className="text-accent font-mono-num">{fmtInd(indicators?.ema20)}</strong>
            </span>
            <span title="Server-computed EMA(50), null when the series is too short">
              EMA50: <strong className="text-violet font-mono-num">{fmtInd(indicators?.ema50)}</strong>
            </span>
            <span title="Server-computed RSI(14), null when the series is too short">
              RSI14: <strong className="text-violet font-mono-num">{fmtInd(indicators?.rsi14)}</strong>
            </span>
            <span title="Server-computed MACD, null when the series is too short">
              MACD: <strong className="text-positive font-mono-num">{fmtInd(indicators?.macd)}</strong>
            </span>
            <span title="Server-computed Bollinger(20,2σ), null when the series is too short">
              BB: <strong className="text-violet font-mono-num">
                {indicators?.bollinger
                  ? `${indicators.bollinger.upper}/${indicators.bollinger.middle}/${indicators.bollinger.lower}`
                  : "—"}
              </strong>
            </span>
          </div>

          {/* Position overlays count */}
          <div className="flex items-center gap-1.5 border-l border-border-subtle pl-2">
            <span className="px-2 py-0.5 rounded text-[10px] flex items-center gap-1 bg-positive-bg text-positive border border-positive font-bold">
              <Layers className="w-3 h-3 text-positive" />
              Positions ({symbolPositions.length})
            </span>
          </div>
        </div>
      )}

      {/* 3. MAIN CHART BODY: NATIVE SVG ENGINE vs TRADINGVIEW WIDGET */}
      <div className="flex-1 relative bg-[var(--color-surface-deep)] overflow-hidden flex">
        {chartEngine === 'TRADINGVIEW' ? (
          /* TRADINGVIEW OFFICIAL ADVANCED WIDGET EMBED */
          <div className="w-full h-[540px] relative bg-[var(--color-surface-0)] flex flex-col items-center justify-center">
            {/* Embedded TradingView Advanced Real-Time Widget */}
            <iframe
              id={`tradingview_widget_${symbol.replace(/[^a-zA-Z0-9]/g, '_')}`}
              title={`TradingView Chart - ${symbol}`}
              src={`https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=${encodeURIComponent(
                tvSymbol
              )}&interval=${timeframe === '1m' ? '1' : timeframe === '5m' ? '5' : timeframe === '15m' ? '15' : timeframe === '1h' ? '60' : timeframe === '4h' ? '240' : 'D'}&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=0a0c10&studies=${encodeURIComponent(
                JSON.stringify(['MASimple@tv-basicstudies', 'RSI@tv-basicstudies', 'Volume@tv-basicstudies'])
              )}&theme=dark&style=1&timezone=exchange&withdateranges=1&showpopupbutton=1&popupwidth=1000&popupheight=650`}
              className="w-full h-full border-0"
              allowFullScreen
            />

            {/* TradingView API Sync Overlay Banner */}
            <div className="absolute top-2 right-2 bg-surface-sunken backdrop-blur-md border border-violet rounded px-2.5 py-1 text-[10px] text-text flex items-center gap-2 pointer-events-auto">
              <span className="w-2 h-2 rounded-full bg-positive animate-ping" />
              <span>TradingView Feed: <strong className="text-accent font-mono">{tvSymbol}</strong></span>
              {onOpenSettings && (
                <button
                  onClick={onOpenSettings}
                  className="text-violet hover:text-violet underline text-[9px]"
                >
                  Configure API
                </button>
              )}
            </div>
          </div>
        ) : candlesQ.loading && bars.length === 0 ? (
          <div className="w-full p-8 text-xs text-text-muted font-mono">
            Loading real bars from /api/v1/market/candles…
          </div>
        ) : candlesQ.error && bars.length === 0 ? (
          <div className="w-full">
            <Unavailable title="Candle feed unavailable" reason={candlesQ.error} />
          </div>
        ) : candlesQ.data && candlesQ.data.available === false && bars.length === 0 ? (
          <div className="w-full">
            <Unavailable title="Candle feed unavailable" reason={candlesQ.data.reason} />
          </div>
        ) : bars.length === 0 ? (
          <div className="w-full p-8 text-center">
            <div className="text-[11px] text-text font-semibold font-mono">No bars for {symbol} ({timeframe}) yet</div>
            <div className="text-[10px] text-text-subtle mt-1 font-mono">
              The feed answered but carried no candles. Press Refresh to fetch the latest real bar.
            </div>
          </div>
        ) : (
          /* NATIVE SVG ENGINE OVER REAL BARS */
          <div className="w-full flex-1 relative select-none">
            {/* OHLCV Crosshair Inspection Banner */}
            <div className="absolute top-2 left-3 z-10 bg-surface-sunken backdrop-blur-sm border border-border-subtle rounded px-2.5 py-1 text-[10px] flex flex-wrap items-center gap-3 text-text font-mono">
              <div>O: <span className="text-text-strong font-bold">{formatPrice((hoveredCandle ?? latest)?.open, symbol)}</span></div>
              <div>H: <span className="text-positive font-bold">{formatPrice((hoveredCandle ?? latest)?.high, symbol)}</span></div>
              <div>L: <span className="text-destructive font-bold">{formatPrice((hoveredCandle ?? latest)?.low, symbol)}</span></div>
              <div>C: <span className="text-text-strong font-bold">{formatPrice((hoveredCandle ?? latest)?.close, symbol)}</span></div>
              <div>Vol: <span className="text-accent font-bold">{((hoveredCandle ?? latest)?.volume ?? 0).toLocaleString()}</span></div>
            </div>

            {/* SVG Candlestick Drawing Layer */}
            <svg
              ref={svgRef}
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              className="w-full h-full min-h-[460px] cursor-crosshair"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            >
              <defs>
                                {/* Area Gradient for Line/Area chart style */}
                <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0.0" />
                </linearGradient>

                <linearGradient id="bullVolume" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-positive)" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="var(--color-positive)" stopOpacity="0.1" />
                </linearGradient>

                <linearGradient id="bearVolume" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-destructive)" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="var(--color-destructive)" stopOpacity="0.1" />
                </linearGradient>
              </defs>

              {/* Background Grid Lines */}
              {[0.2, 0.4, 0.6, 0.8].map(ratio => {
                const y = chartHeight * ratio;
                const gridPrice = maxPrice - ratio * priceRange;
                return (
                  <g key={ratio}>
                    <line x1="10" y1={y} x2={chartWidth - 60} y2={y} stroke="var(--color-text-strong)" strokeOpacity="0.05" strokeDasharray="3 3" />
                    <text x={chartWidth - 55} y={y + 3} fill="var(--color-text-subtle)" fontSize="9" fontFamily="monospace">
                      {formatPrice(gridPrice, symbol)}
                    </text>
                  </g>
                );
              })}

              {/* Volume Profile Histogram (Bottom of Main Chart) */}
              {bars.map((c, i) => {
                const x = getX(i);
                const volHeight = (c.volume / maxVolume) * 70;
                const y = chartHeight - volHeight - 5;
                const isBull = c.close >= c.open;
                return (
                  <rect
                    key={`vol-${i}`}
                    x={x - candleBarWidth / 2}
                    y={y}
                    width={candleBarWidth}
                    height={volHeight}
                    fill={isBull ? 'url(#bullVolume)' : 'url(#bearVolume)'}
                  />
                );
              })}

              {/* Area Chart Mode */}
              {chartStyle === 'AREA' && (
                <>
                  <polygon
                    points={`
                      ${getX(0)},${chartHeight - 10}
                      ${bars.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')}
                      ${getX(bars.length - 1)},${chartHeight - 10}
                    `}
                    fill="url(#areaGradient)"
                  />
                  <polyline
                    points={bars.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')}
                    fill="none"
                    stroke="var(--color-accent)"
                    strokeWidth="2"
                  />
                </>
              )}

              {/* Line Chart Mode */}
              {chartStyle === 'LINE' && (
                <polyline
                  points={bars.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')}
                  fill="none"
                  stroke="var(--color-accent-info)"
                  strokeWidth="2"
                />
              )}

              {/* Candlestick & Heikin Ashi Mode */}
              {(chartStyle === 'CANDLE' || chartStyle === 'HEIKIN') && bars.map((c, i) => {
                const x = getX(i);
                const isBull = c.close >= c.open;
                const highY = getY(c.high);
                const lowY = getY(c.low);
                const openY = getY(c.open);
                const closeY = getY(c.close);
                const bodyY = Math.min(openY, closeY);
                const bodyHeight = Math.max(2, Math.abs(closeY - openY));

                const color = isBull ? 'var(--color-positive)' : 'var(--color-destructive)';

                return (
                  <g key={`candle-${i}`} className="transition-all hover:opacity-100">
                    {/* Wick */}
                    <line
                      x1={x}
                      y1={highY}
                      x2={x}
                      y2={lowY}
                      stroke={color}
                      strokeWidth="1.2"
                    />
                    {/* Body */}
                    <rect
                      x={x - candleBarWidth / 2}
                      y={bodyY}
                      width={candleBarWidth}
                      height={bodyHeight}
                      fill={color}
                      stroke={color}
                      strokeWidth="0.5"
                      rx="0.5"
                    />
                  </g>
                );
              })}

              {/* Active Positions on Chart (live /positions rows) */}
              {symbolPositions.map(pos => {
                const entryY = getY(pos.entryPrice);
                const slY = pos.stopLossPrice ? getY(pos.stopLossPrice) : null;
                const tpY = pos.takeProfitPrice ? getY(pos.takeProfitPrice) : null;

                return (
                  <g key={pos.id} className="position-overlay">
                    {/* Entry Price Line */}
                    <line
                      x1="10"
                      y1={entryY}
                      x2={chartWidth - 60}
                      y2={entryY}
                      stroke="var(--color-positive)"
                      strokeWidth="1.5"
                      strokeDasharray="2 2"
                    />
                    <rect
                      x={chartWidth - 175}
                      y={entryY - 9}
                      width="115"
                      height="16"
                      fill="var(--color-positive-bg)"
                      stroke="var(--color-positive)"
                      strokeWidth="1"
                      rx="3"
                    />
                    <text x={chartWidth - 170} y={entryY + 3} fill="var(--color-positive-soft)" fontSize="8" fontWeight="bold">
                      POS: {pos.side} {pos.size} @ {formatPrice(pos.entryPrice, symbol)}
                    </text>

                    {/* Stop Loss Line */}
                    {slY && (
                      <>
                        <line
                          x1="10"
                          y1={slY}
                          x2={chartWidth - 60}
                          y2={slY}
                          stroke="var(--color-destructive)"
                          strokeWidth="1"
                          strokeDasharray="4 2"
                        />
                        <rect
                          x={chartWidth - 110}
                          y={slY - 8}
                          width="50"
                          height="14"
                          fill="var(--color-destructive-bg)"
                          stroke="var(--color-destructive)"
                          strokeWidth="0.8"
                          rx="2"
                        />
                        <text x={chartWidth - 105} y={slY + 2} fill="var(--color-destructive-soft)" fontSize="8" fontWeight="bold">
                          SL {formatPrice(pos.stopLossPrice!, symbol)}
                        </text>
                      </>
                    )}

                    {/* Take Profit Line */}
                    {tpY && (
                      <>
                        <line
                          x1="10"
                          y1={tpY}
                          x2={chartWidth - 60}
                          y2={tpY}
                          stroke="var(--color-accent-soft)"
                          strokeWidth="1"
                          strokeDasharray="4 2"
                        />
                        <rect
                          x={chartWidth - 110}
                          y={tpY - 8}
                          width="50"
                          height="14"
                          fill="var(--color-info-bg)"
                          stroke="var(--color-accent-soft)"
                          strokeWidth="0.8"
                          rx="2"
                        />
                        <text x={chartWidth - 105} y={tpY + 2} fill="var(--color-accent-glow)" fontSize="8" fontWeight="bold">
                          TP {formatPrice(pos.takeProfitPrice!, symbol)}
                        </text>
                      </>
                    )}
                  </g>
                );
              })}

              {/* Current Price Ticker Line (Right Edge) */}
              {latest && (() => {
                const currentY = getY(latest.close);
                return (
                  <g className="live-price-marker">
                    <line
                      x1="10"
                      y1={currentY}
                      x2={chartWidth - 60}
                      y2={currentY}
                      stroke="var(--color-accent)"
                      strokeWidth="1"
                      strokeDasharray="2 1"
                    />
                    <rect
                      x={chartWidth - 58}
                      y={currentY - 9}
                      width="55"
                      height="18"
                      fill="var(--color-accent)"
                      rx="3"
                    />
                    <text
                      x={chartWidth - 54}
                      y={currentY + 4}
                      fill="var(--color-text-on-accent)"
                      fontSize="9"
                      fontWeight="bold"
                      fontFamily="monospace"
                    >
                      {formatPrice(latest.close, symbol)}
                    </text>
                  </g>
                );
              })()}

              {/* Interactive Crosshair Cursor */}
              {mouseCoords && (
                <g className="crosshair">
                  {/* Vertical Crosshair Line */}
                  <line
                    x1={mouseCoords.x}
                    y1="10"
                    x2={mouseCoords.x}
                    y2={chartHeight - 10}
                    stroke="var(--color-text-muted)"
                    strokeWidth="0.8"
                    strokeDasharray="2 2"
                  />
                  {/* Horizontal Crosshair Line */}
                  <line
                    x1="10"
                    y1={mouseCoords.y}
                    x2={chartWidth - 60}
                    y2={mouseCoords.y}
                    stroke="var(--color-text-muted)"
                    strokeWidth="0.8"
                    strokeDasharray="2 2"
                  />
                  {/* Price Tag at Cursor */}
                  <rect
                    x={chartWidth - 58}
                    y={mouseCoords.y - 8}
                    width="55"
                    height="16"
                    fill="var(--color-text-dim)"
                    stroke="var(--color-text-muted)"
                    strokeWidth="0.8"
                    rx="2"
                  />
                  <text
                    x={chartWidth - 54}
                    y={mouseCoords.y + 4}
                    fill="var(--color-text-strong)"
                    fontSize="8"
                    fontFamily="monospace"
                  >
                    {formatPrice(mouseCoords.price, symbol)}
                  </text>
                </g>
              )}
            </svg>
          </div>
        )}
      </div>

      {/* 4. FOOTER STATUS BAR */}
      <div className="bg-[var(--color-surface-rail)] border-t border-border-subtle px-3.5 py-1.5 flex flex-wrap items-center justify-between text-[10px] text-text-muted">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${candlesQ.error ? 'bg-destructive' : 'bg-positive'}`} />
            Feed: <strong className="text-text-strong">/api/v1/market/candles</strong>
          </span>
          <span className="text-text-subtle">|</span>
          <span>Timezone: <strong className="text-text-strong">{settings.marketClockTimezone || 'UTC'}</strong></span>
          <span className="text-text-subtle">|</span>
          <span>Bars: <strong className="text-text-strong">{bars.length} real</strong></span>
          {feedSource && (
            <>
              <span className="text-text-subtle">|</span>
              <span className="truncate max-w-[220px]" title={feedSource}>src: {feedSource.slice(0, 28)}…</span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 text-[9px] text-text-subtle">
          {candlesQ.error ? (
            <span className="text-destructive">last fetch failed — showing cached bars</span>
          ) : (
            <span>staging via the order ticket (submission not wired)</span>
          )}
        </div>
      </div>
    </div>
  );
};

// Price formatting helper for diverse asset classes
function formatPrice(val: number | undefined, symbol: string): string {
  if (val === undefined || isNaN(val)) return '0.00';
  if (symbol.startsWith('PM-')) {
    return `$${val.toFixed(2)}`; // Polymarket odds contract
  }
  if (symbol.includes('JPY') || symbol.includes('7203') || symbol.includes('RELIANCE')) {
    return val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  if (symbol.includes('EUR') || symbol.includes('GBP') || symbol.includes('BRL')) {
    return val.toFixed(4);
  }
  if (val >= 1000) {
    return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `$${val.toFixed(2)}`;
}
