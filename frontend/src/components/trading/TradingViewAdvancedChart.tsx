import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  BarChart2, 
   
   
   
  Layers, 
  Maximize2, 
  Minimize2, 
   
   
  Activity, 
   
   
   
  Sparkles, 
   
  ArrowUpRight, 
  ArrowDownRight,
  Camera,
  Play,


} from 'lucide-react';
import { Position,  SystemSettings } from '../../types';

export interface CandleData {
  time: string;
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
  price: number;
  change24hPct: number;
  high24h: number;
  low24h: number;
  volume24h: string;
  settings: SystemSettings;
  activePositions?: Position[];
  onQuickOrder?: (side: 'BUY' | 'SELL', price: number) => void;
  onOpenSettings?: () => void;
}

export type TimeFrame = '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W';
export type ChartStyle = 'CANDLE' | 'HEIKIN' | 'LINE' | 'AREA';

export const TradingViewAdvancedChart: React.FC<TradingViewAdvancedChartProps> = ({
  symbol,
  name,
  category,
  price,
  change24hPct,
  high24h,
  low24h,
  volume24h,
  settings,
  activePositions = [],
  onQuickOrder,
  onOpenSettings
}) => {
  // Chart Modes: Native Canvas/SVG vs Official TradingView Pro Widget
  const [chartEngine, setChartEngine] = useState<'NATIVE' | 'TRADINGVIEW'>(
    settings.tradingViewApiEnabled ? 'NATIVE' : 'NATIVE'
  );
  const [timeframe, setTimeframe] = useState<TimeFrame>('15m');
  const [chartStyle, setChartStyle] = useState<ChartStyle>('CANDLE');
  
  // Indicators Toggle States
  const [showEMA, setShowEMA] = useState<boolean>(true);
  const [showBB, setShowBB] = useState<boolean>(false);
  const [showVWAP, setShowVWAP] = useState<boolean>(true);
  const [showRSI, setShowRSI] = useState<boolean>(true);
  const [showMACD, setShowMACD] = useState<boolean>(false);
  const [showVolume] = useState<boolean>(true);
  const [showAgentOverlays, setShowAgentOverlays] = useState<boolean>(true);
  const [showPositionsOnChart, setShowPositionsOnChart] = useState<boolean>(true);
  
  // Interactive Tools
  const [hoveredCandle, setHoveredCandle] = useState<CandleData | null>(null);
  const [mouseCoords, setMouseCoords] = useState<{ x: number; y: number; price: number } | null>(null);
  const [isLiveTicking, setIsLiveTicking] = useState<boolean>(true);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [snapshotTaken, setSnapshotTaken] = useState<boolean>(false);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Generate deterministic realistic synthetic candlestick history for the selected symbol & timeframe
  const [candles, setCandles] = useState<CandleData[]>(() => {
    return generateCandles(symbol, price, 60, timeframe);
  });

  // Re-generate candles when symbol or timeframe changes
  useEffect(() => {
    setCandles(generateCandles(symbol, price, 60, timeframe));
    setHoveredCandle(null);
  }, [symbol, timeframe]);

  // Live real-time tick simulator
  useEffect(() => {
    if (!isLiveTicking) return;

    const interval = setInterval(() => {
      setCandles(prev => {
        if (prev.length === 0) return prev;
        const last = { ...prev[prev.length - 1] };
        
        // Random micro tick volatility based on price
        const tickPct = (Math.random() - 0.49) * 0.003;
        const newClose = +(last.close * (1 + tickPct)).toFixed(symbol.includes('JPY') || symbol.includes('7203') ? 1 : symbol.includes('PM-') ? 4 : 2);
        
        last.close = newClose;
        last.high = Math.max(last.high, newClose);
        last.low = Math.min(last.low, newClose);
        last.volume += Math.floor(Math.random() * 50) + 5;
        
        const updated = [...prev.slice(0, prev.length - 1), last];
        return calculateTechnicalIndicators(updated);
      });
    }, 1200);

    return () => clearInterval(interval);
  }, [isLiveTicking, symbol]);

  // Compute bounding box & scales
  const chartHeight = showRSI || showMACD ? 380 : 480;
  const subPanelHeight = 90;
  const chartWidth = 840; // responsive SVG viewBox

  const { minPrice, maxPrice, priceRange, maxVolume } = useMemo(() => {
    if (candles.length === 0) return { minPrice: 0, maxPrice: 1, priceRange: 1, minVolume: 0, maxVolume: 100 };
    
    let min = Math.min(...candles.map(c => c.low));
    let max = Math.max(...candles.map(c => c.high));
    
    // Include BB or positions in range if enabled
    if (showBB) {
      candles.forEach(c => {
        if (c.bbUpper) max = Math.max(max, c.bbUpper);
        if (c.bbLower) min = Math.min(min, c.bbLower);
      });
    }

    const padding = (max - min) * 0.08 || min * 0.02;
    const maxVol = Math.max(...candles.map(c => c.volume), 100);

    return {
      minPrice: min - padding,
      maxPrice: max + padding,
      priceRange: max - min + padding * 2 || 1,
      minVolume: 0,
      maxVolume: maxVol
    };
  }, [candles, showBB]);

  // Price to Y coordinate mapper
  const getY = (val: number) => {
    return chartHeight - ((val - minPrice) / priceRange) * (chartHeight - 40) - 20;
  };

  // Time to X coordinate mapper
  const getX = (index: number) => {
    const candleWidth = (chartWidth - 70) / candles.length;
    return 10 + index * candleWidth + candleWidth / 2;
  };

  const candleBarWidth = Math.max(2, ((chartWidth - 70) / candles.length) * 0.65);

  // Active positions for current symbol
  const symbolPositions = activePositions.filter(p => p.symbol === symbol);

  // TradingView Symbol Translation
  const tvSymbol = settings.tradingViewSymbolMapping?.[symbol] || (
    symbol.includes('/') ? `BINANCE:${symbol.replace('/', '')}` : `NASDAQ:${symbol}`
  );

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Scale to viewBox coordinates
    const scaleX = chartWidth / rect.width;
    const scaleY = (chartHeight + (showRSI ? subPanelHeight : 0) + (showMACD ? subPanelHeight : 0)) / rect.height;
    
    const svgX = x * scaleX;
    const svgY = y * scaleY;

    // Calculate price at cursor
    const cursorPrice = maxPrice - (svgY / chartHeight) * priceRange;

    // Find nearest candle
    const candleWidth = (chartWidth - 70) / candles.length;
    const candleIndex = Math.min(candles.length - 1, Math.max(0, Math.floor((svgX - 10) / candleWidth)));
    
    setHoveredCandle(candles[candleIndex] || null);
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

  return (
    <div 
      ref={containerRef}
      className={`bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono select-none transition-all ${
        isFullscreen ? 'fixed inset-4 z-50 shadow-2xl border-cyan-500/40 bg-[#07080c]' : ''
      }`}
    >
      {/* 1. TOP PRO-CHART HEADER & TICKER BANNER */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Left: Asset Ticker Info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-100 text-sm tracking-wider">{symbol}</span>
            <span className="text-[10px] text-slate-400 font-sans hidden sm:inline max-w-[140px] truncate">
              {name}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-700/40 text-[9px] text-cyan-300 font-semibold uppercase">
              {category}
            </span>
          </div>

          <div className="h-4 w-px bg-white/10" />

          {/* Real-Time Price & 24h Change */}
          <div className="flex items-baseline gap-2">
            <span className="text-base font-bold text-slate-100 font-mono-num">
              {formatPrice(candles[candles.length - 1]?.close || price, symbol)}
            </span>
            <span className={`flex items-center gap-0.5 text-[11px] font-bold ${
              change24hPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {change24hPct >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {change24hPct >= 0 ? '+' : ''}{change24hPct.toFixed(2)}%
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-4 text-[10px] text-slate-400 pl-2 border-l border-white/10">
            <div>24h High: <span className="text-slate-200 font-mono-num">{formatPrice(high24h, symbol)}</span></div>
            <div>24h Low: <span className="text-slate-200 font-mono-num">{formatPrice(low24h, symbol)}</span></div>
            <div>24h Vol: <span className="text-slate-200 font-mono-num">{volume24h}</span></div>
          </div>
        </div>

        {/* Right: Chart Controls & Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Native vs TradingView Pro API Engine Toggle */}
          <div className="bg-black/50 border border-white/10 p-0.5 rounded-lg flex items-center gap-0.5">
            <button
              onClick={() => setChartEngine('NATIVE')}
              className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all flex items-center gap-1 ${
                chartEngine === 'NATIVE'
                  ? 'bg-cyan-600 text-white shadow-[0_0_10px_rgba(0,240,255,0.3)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`}
              title="Ultra Low-Latency Native Canvas Engine"
            >
              <Activity className="w-3 h-3" />
              Native Low-Latency
            </button>
            <button
              onClick={() => setChartEngine('TRADINGVIEW')}
              className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all flex items-center gap-1 ${
                chartEngine === 'TRADINGVIEW'
                  ? 'bg-indigo-600 text-white shadow-[0_0_10px_rgba(99,102,241,0.3)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`}
              title="Official TradingView Advanced Real-Time Charting Library"
            >
              <BarChart2 className="w-3 h-3" />
              TradingView API Pro
            </button>
          </div>

          {/* Timeframe Selector */}
          <div className="hidden md:flex bg-black/40 border border-white/10 rounded p-0.5 gap-0.5 text-[10px]">
            {(['1m', '5m', '15m', '1h', '4h', '1D', '1W'] as TimeFrame[]).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-0.5 rounded font-medium transition-all ${
                  timeframe === tf
                    ? 'bg-white/15 text-cyan-300 font-bold border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.05]'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Live Ticking Stream Pause/Play */}
          <button
            onClick={() => setIsLiveTicking(!isLiveTicking)}
            className={`p-1.5 rounded border text-[10px] transition-all flex items-center gap-1 ${
              isLiveTicking
                ? 'bg-emerald-950/40 text-emerald-300 border-emerald-700/40 animate-pulse'
                : 'bg-white/[0.04] text-slate-400 border-white/10 hover:text-slate-200'
            }`}
            title={isLiveTicking ? 'Real-Time Feed Active (Click to Pause)' : 'Feed Paused (Click to Stream)'}
          >
            {isLiveTicking ? <Activity className="w-3 h-3 text-emerald-400" /> : <Play className="w-3 h-3" />}
            <span className="text-[9px] font-bold uppercase">{isLiveTicking ? 'LIVE' : 'PAUSED'}</span>
          </button>

          {/* Screenshot / Snapshot */}
          <button
            onClick={handleTakeSnapshot}
            className="p-1.5 rounded bg-white/[0.04] border border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08] relative"
            title="Capture Chart Snapshot"
          >
            <Camera className="w-3.5 h-3.5" />
            {snapshotTaken && (
              <span className="absolute -top-7 right-0 bg-cyan-900 border border-cyan-400 text-cyan-100 text-[9px] px-1.5 py-0.5 rounded shadow-lg whitespace-nowrap">
                Captured!
              </span>
            )}
          </button>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded bg-white/[0.04] border border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08]"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen Chart'}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. SECONDARY TOOLBAR: INDICATORS & DRAWING TOOLS (For Native Mode) */}
      {chartEngine === 'NATIVE' && (
        <div className="bg-[#090b10] border-b border-white/[0.06] px-3.5 py-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px]">
          {/* Chart Style Switcher */}
          <div className="flex items-center gap-1 text-[10px]">
            <span className="text-slate-400 text-[9px] uppercase font-bold mr-1">Style:</span>
            {(['CANDLE', 'HEIKIN', 'LINE', 'AREA'] as ChartStyle[]).map(style => (
              <button
                key={style}
                onClick={() => setChartStyle(style)}
                className={`px-2 py-0.5 rounded transition-all ${
                  chartStyle === style
                    ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-700/40 font-bold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
              >
                {style}
              </button>
            ))}
          </div>

          {/* Technical Indicator Toggles */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 text-[9px] uppercase font-bold mr-1">Indicators:</span>
            <button
              onClick={() => setShowEMA(!showEMA)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all ${
                showEMA ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-600/50' : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
            >
              EMA (20/50/200)
            </button>
            <button
              onClick={() => setShowBB(!showBB)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all ${
                showBB ? 'bg-indigo-950/80 text-indigo-300 border border-indigo-600/50' : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
            >
              Bollinger (20,2σ)
            </button>
            <button
              onClick={() => setShowVWAP(!showVWAP)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all ${
                showVWAP ? 'bg-amber-950/80 text-amber-300 border border-amber-600/50' : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
            >
              VWAP
            </button>
            <button
              onClick={() => setShowRSI(!showRSI)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all ${
                showRSI ? 'bg-purple-950/80 text-purple-300 border border-purple-600/50' : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
            >
              RSI (14)
            </button>
            <button
              onClick={() => setShowMACD(!showMACD)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all ${
                showMACD ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-600/50' : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
            >
              MACD
            </button>
          </div>

          {/* AI & Position Overlays */}
          <div className="flex items-center gap-1.5 border-l border-white/10 pl-2">
            <button
              onClick={() => setShowAgentOverlays(!showAgentOverlays)}
              className={`px-2 py-0.5 rounded text-[10px] flex items-center gap-1 transition-all ${
                showAgentOverlays 
                  ? 'bg-rose-950/60 text-rose-300 border border-rose-700/50 font-bold' 
                  : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
              title="Show AI Agent Debate Entries, Stop Loss & Target Overlays"
            >
              <Sparkles className="w-3 h-3 text-rose-400" />
              Agent Signals
            </button>

            <button
              onClick={() => setShowPositionsOnChart(!showPositionsOnChart)}
              className={`px-2 py-0.5 rounded text-[10px] flex items-center gap-1 transition-all ${
                showPositionsOnChart 
                  ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 font-bold' 
                  : 'text-slate-400 hover:bg-white/[0.04]'
              }`}
              title="Show Open Position Lines & Risk Triggers"
            >
              <Layers className="w-3 h-3 text-emerald-400" />
              Positions ({symbolPositions.length})
            </button>
          </div>
        </div>
      )}

      {/* 3. MAIN CHART BODY: NATIVE CANVAS/SVG ENGINE vs TRADINGVIEW WIDGET */}
      <div className="flex-1 relative bg-[#06070a] overflow-hidden flex">
        {chartEngine === 'TRADINGVIEW' ? (
          /* TRADINGVIEW OFFICIAL ADVANCED WIDGET EMBED */
          <div className="w-full h-[540px] relative bg-[#08090d] flex flex-col items-center justify-center">
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
            <div className="absolute top-2 right-2 bg-black/80 backdrop-blur-md border border-indigo-500/30 rounded px-2.5 py-1 text-[10px] text-slate-300 flex items-center gap-2 pointer-events-auto">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>TradingView Feed: <strong className="text-cyan-300 font-mono">{tvSymbol}</strong></span>
              {onOpenSettings && (
                <button 
                  onClick={onOpenSettings}
                  className="text-indigo-300 hover:text-indigo-100 underline text-[9px]"
                >
                  Configure API
                </button>
              )}
            </div>
          </div>
        ) : (
          /* HIGH-SPEED NATIVE CANDLESTICK & TECHNICAL INDICATOR SVG ENGINE */
          <div className="w-full flex-1 relative select-none">
            {/* OHLCV Crosshair Inspection Banner */}
            <div className="absolute top-2 left-3 z-10 bg-black/75 backdrop-blur-sm border border-white/10 rounded px-2.5 py-1 text-[10px] flex flex-wrap items-center gap-3 text-slate-300 font-mono">
              <div>O: <span className="text-slate-100 font-bold">{formatPrice(hoveredCandle ? hoveredCandle.open : candles[candles.length - 1]?.open, symbol)}</span></div>
              <div>H: <span className="text-emerald-400 font-bold">{formatPrice(hoveredCandle ? hoveredCandle.high : candles[candles.length - 1]?.high, symbol)}</span></div>
              <div>L: <span className="text-rose-400 font-bold">{formatPrice(hoveredCandle ? hoveredCandle.low : candles[candles.length - 1]?.low, symbol)}</span></div>
              <div>C: <span className="text-slate-100 font-bold">{formatPrice(hoveredCandle ? hoveredCandle.close : candles[candles.length - 1]?.close, symbol)}</span></div>
              <div>Vol: <span className="text-cyan-300 font-bold">{(hoveredCandle ? hoveredCandle.volume : candles[candles.length - 1]?.volume).toLocaleString()}</span></div>
              {showRSI && hoveredCandle?.rsi && (
                <div className="text-purple-300">RSI(14): <span className="font-bold">{hoveredCandle.rsi.toFixed(1)}</span></div>
              )}
              {showVWAP && hoveredCandle?.vwap && (
                <div className="text-amber-300">VWAP: <span className="font-bold">{formatPrice(hoveredCandle.vwap, symbol)}</span></div>
              )}
            </div>

            {/* SVG Candlestick & Indicator Drawing Layer */}
            <svg
              ref={svgRef}
              viewBox={`0 0 ${chartWidth} ${chartHeight + (showRSI ? subPanelHeight : 0) + (showMACD ? subPanelHeight : 0)}`}
              className="w-full h-full min-h-[460px] cursor-crosshair"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            >
              <defs>
                {/* Area Gradient for Line/Area chart style */}
                <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#00f0ff" stopOpacity="0.0" />
                </linearGradient>

                <linearGradient id="bullVolume" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#10b981" stopOpacity="0.1" />
                </linearGradient>

                <linearGradient id="bearVolume" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.1" />
                </linearGradient>

                <linearGradient id="bbGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity="0.12" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.04" />
                </linearGradient>
              </defs>

              {/* Background Grid Lines */}
              {[0.2, 0.4, 0.6, 0.8].map(ratio => {
                const y = chartHeight * ratio;
                const gridPrice = maxPrice - ratio * priceRange;
                return (
                  <g key={ratio}>
                    <line x1="10" y1={y} x2={chartWidth - 60} y2={y} stroke="#ffffff" strokeOpacity="0.05" strokeDasharray="3 3" />
                    <text x={chartWidth - 55} y={y + 3} fill="#64748b" fontSize="9" fontFamily="monospace">
                      {formatPrice(gridPrice, symbol)}
                    </text>
                  </g>
                );
              })}

              {/* Volume Profile Histogram (Bottom of Main Chart) */}
              {showVolume && candles.map((c, i) => {
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

              {/* Bollinger Bands Shaded Area */}
              {showBB && (
                <>
                  <polygon
                    points={`
                      ${candles.map((c, i) => `${getX(i)},${getY(c.bbUpper || c.high)}`).join(' ')} 
                      ${candles.slice().reverse().map((c, i) => `${getX(candles.length - 1 - i)},${getY(c.bbLower || c.low)}`).join(' ')}
                    `}
                    fill="url(#bbGradient)"
                  />
                  {/* BB Upper */}
                  <polyline
                    points={candles.map((c, i) => `${getX(i)},${getY(c.bbUpper || c.high)}`).join(' ')}
                    fill="none"
                    stroke="#818cf8"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                    opacity="0.6"
                  />
                  {/* BB Lower */}
                  <polyline
                    points={candles.map((c, i) => `${getX(i)},${getY(c.bbLower || c.low)}`).join(' ')}
                    fill="none"
                    stroke="#818cf8"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                    opacity="0.6"
                  />
                </>
              )}

              {/* EMA 20 (Cyan), EMA 50 (Violet), EMA 200 (Amber) */}
              {showEMA && (
                <>
                  {/* EMA 20 */}
                  <polyline
                    points={candles.filter(c => c.ema20).map((c, i) => `${getX(i)},${getY(c.ema20!)}`).join(' ')}
                    fill="none"
                    stroke="#00f0ff"
                    strokeWidth="1.5"
                    opacity="0.85"
                  />
                  {/* EMA 50 */}
                  <polyline
                    points={candles.filter(c => c.ema50).map((c, i) => `${getX(i)},${getY(c.ema50!)}`).join(' ')}
                    fill="none"
                    stroke="#a855f7"
                    strokeWidth="1.2"
                    opacity="0.75"
                  />
                  {/* EMA 200 */}
                  <polyline
                    points={candles.filter(c => c.ema200).map((c, i) => `${getX(i)},${getY(c.ema200!)}`).join(' ')}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="1.5"
                    opacity="0.75"
                  />
                </>
              )}

              {/* VWAP Line */}
              {showVWAP && (
                <polyline
                  points={candles.filter(c => c.vwap).map((c, i) => `${getX(i)},${getY(c.vwap!)}`).join(' ')}
                  fill="none"
                  stroke="#eab308"
                  strokeWidth="1.2"
                  strokeDasharray="4 2"
                  opacity="0.9"
                />
              )}

              {/* Area Chart Mode */}
              {chartStyle === 'AREA' && (
                <>
                  <polygon
                    points={`
                      ${getX(0)},${chartHeight - 10} 
                      ${candles.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')} 
                      ${getX(candles.length - 1)},${chartHeight - 10}
                    `}
                    fill="url(#areaGradient)"
                  />
                  <polyline
                    points={candles.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')}
                    fill="none"
                    stroke="#00f0ff"
                    strokeWidth="2"
                  />
                </>
              )}

              {/* Line Chart Mode */}
              {chartStyle === 'LINE' && (
                <polyline
                  points={candles.map((c, i) => `${getX(i)},${getY(c.close)}`).join(' ')}
                  fill="none"
                  stroke="#38bdf8"
                  strokeWidth="2"
                />
              )}

              {/* Candlestick & Heikin Ashi Mode */}
              {(chartStyle === 'CANDLE' || chartStyle === 'HEIKIN') && candles.map((c, i) => {
                const x = getX(i);
                const isBull = c.close >= c.open;
                const highY = getY(c.high);
                const lowY = getY(c.low);
                const openY = getY(c.open);
                const closeY = getY(c.close);
                const bodyY = Math.min(openY, closeY);
                const bodyHeight = Math.max(2, Math.abs(closeY - openY));

                const color = isBull ? '#10b981' : '#f43f5e';

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

              {/* AI Agent Signals / Consensus Overlays */}
              {showAgentOverlays && (
                <g className="agent-overlays">
                  {/* Consensus Buy Zone Marker */}
                  <line
                    x1="10"
                    y1={getY(price * 0.985)}
                    x2={chartWidth - 60}
                    y2={getY(price * 0.985)}
                    stroke="#00f0ff"
                    strokeWidth="1"
                    strokeDasharray="4 3"
                  />
                  <rect
                    x="15"
                    y={getY(price * 0.985) - 9}
                    width="120"
                    height="16"
                    fill="#083344"
                    stroke="#06b6d4"
                    strokeWidth="0.8"
                    rx="3"
                  />
                  <text x="22" y={getY(price * 0.985) + 3} fill="#67e8f9" fontSize="8" fontWeight="bold">
                    ★ AGENT BUY TARGET: {formatPrice(price * 0.985, symbol)}
                  </text>
                </g>
              )}

              {/* Active Positions on Chart */}
              {showPositionsOnChart && symbolPositions.map(pos => {
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
                      stroke="#10b981"
                      strokeWidth="1.5"
                      strokeDasharray="2 2"
                    />
                    <rect
                      x={chartWidth - 175}
                      y={entryY - 9}
                      width="115"
                      height="16"
                      fill="#064e3b"
                      stroke="#10b981"
                      strokeWidth="1"
                      rx="3"
                    />
                    <text x={chartWidth - 170} y={entryY + 3} fill="#6ee7b7" fontSize="8" fontWeight="bold">
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
                          stroke="#ef4444"
                          strokeWidth="1"
                          strokeDasharray="4 2"
                        />
                        <rect
                          x={chartWidth - 110}
                          y={slY - 8}
                          width="50"
                          height="14"
                          fill="#450a0a"
                          stroke="#ef4444"
                          strokeWidth="0.8"
                          rx="2"
                        />
                        <text x={chartWidth - 105} y={slY + 2} fill="#fca5a5" fontSize="8" fontWeight="bold">
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
                          stroke="#06b6d4"
                          strokeWidth="1"
                          strokeDasharray="4 2"
                        />
                        <rect
                          x={chartWidth - 110}
                          y={tpY - 8}
                          width="50"
                          height="14"
                          fill="#083344"
                          stroke="#06b6d4"
                          strokeWidth="0.8"
                          rx="2"
                        />
                        <text x={chartWidth - 105} y={tpY + 2} fill="#67e8f9" fontSize="8" fontWeight="bold">
                          TP {formatPrice(pos.takeProfitPrice!, symbol)}
                        </text>
                      </>
                    )}
                  </g>
                );
              })}

              {/* Current Price Ticker Line (Right Edge) */}
              {(() => {
                const currentY = getY(candles[candles.length - 1]?.close || price);
                return (
                  <g className="live-price-marker">
                    <line
                      x1="10"
                      y1={currentY}
                      x2={chartWidth - 60}
                      y2={currentY}
                      stroke="#00f0ff"
                      strokeWidth="1"
                      strokeDasharray="2 1"
                    />
                    <rect
                      x={chartWidth - 58}
                      y={currentY - 9}
                      width="55"
                      height="18"
                      fill="#00f0ff"
                      rx="3"
                    />
                    <text
                      x={chartWidth - 54}
                      y={currentY + 4}
                      fill="#040810"
                      fontSize="9"
                      fontWeight="bold"
                      fontFamily="monospace"
                    >
                      {formatPrice(candles[candles.length - 1]?.close || price, symbol)}
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
                    stroke="#94a3b8"
                    strokeWidth="0.8"
                    strokeDasharray="2 2"
                  />
                  {/* Horizontal Crosshair Line */}
                  <line
                    x1="10"
                    y1={mouseCoords.y}
                    x2={chartWidth - 60}
                    y2={mouseCoords.y}
                    stroke="#94a3b8"
                    strokeWidth="0.8"
                    strokeDasharray="2 2"
                  />
                  {/* Price Tag at Cursor */}
                  <rect
                    x={chartWidth - 58}
                    y={mouseCoords.y - 8}
                    width="55"
                    height="16"
                    fill="#334155"
                    stroke="#94a3b8"
                    strokeWidth="0.8"
                    rx="2"
                  />
                  <text
                    x={chartWidth - 54}
                    y={mouseCoords.y + 4}
                    fill="#f8fafc"
                    fontSize="8"
                    fontFamily="monospace"
                  >
                    {formatPrice(mouseCoords.price, symbol)}
                  </text>
                </g>
              )}

              {/* SUB-PANEL 1: RSI (14) */}
              {showRSI && (
                <g transform={`translate(0, ${chartHeight})`}>
                  <rect x="10" y="0" width={chartWidth - 70} height={subPanelHeight} fill="#040508" stroke="#ffffff" strokeOpacity="0.08" />
                  
                  {/* RSI Overbought 70 & Oversold 30 Lines */}
                  <line x1="10" y1={subPanelHeight * 0.3} x2={chartWidth - 60} y2={subPanelHeight * 0.3} stroke="#ef4444" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.6" />
                  <line x1="10" y1={subPanelHeight * 0.7} x2={chartWidth - 60} y2={subPanelHeight * 0.7} stroke="#10b981" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.6" />
                  
                  <text x={chartWidth - 55} y={subPanelHeight * 0.3 + 3} fill="#ef4444" fontSize="8">70</text>
                  <text x={chartWidth - 55} y={subPanelHeight * 0.7 + 3} fill="#10b981" fontSize="8">30</text>
                  <text x="16" y="14" fill="#a855f7" fontSize="9" fontWeight="bold">RSI (14)</text>

                  {/* RSI Curve */}
                  <polyline
                    points={candles.filter(c => c.rsi !== undefined).map((c, i) => {
                      const rsiY = subPanelHeight - (c.rsi! / 100) * subPanelHeight;
                      return `${getX(i)},${rsiY}`;
                    }).join(' ')}
                    fill="none"
                    stroke="#c084fc"
                    strokeWidth="1.5"
                  />
                </g>
              )}

              {/* SUB-PANEL 2: MACD (12, 26, 9) */}
              {showMACD && (
                <g transform={`translate(0, ${chartHeight + (showRSI ? subPanelHeight : 0)})`}>
                  <rect x="10" y="0" width={chartWidth - 70} height={subPanelHeight} fill="#040508" stroke="#ffffff" strokeOpacity="0.08" />
                  <line x1="10" y1={subPanelHeight / 2} x2={chartWidth - 60} y2={subPanelHeight / 2} stroke="#ffffff" strokeOpacity="0.1" strokeDasharray="2 2" />
                  <text x="16" y="14" fill="#10b981" fontSize="9" fontWeight="bold">MACD (12, 26, 9)</text>

                  {/* MACD Histogram Bars */}
                  {candles.map((c, i) => {
                    const x = getX(i);
                    const hist = c.macdHist || 0;
                    const barHeight = Math.min(35, Math.abs(hist * 10));
                    const y = hist >= 0 ? subPanelHeight / 2 - barHeight : subPanelHeight / 2;
                    return (
                      <rect
                        key={`macd-hist-${i}`}
                        x={x - candleBarWidth / 2}
                        y={y}
                        width={candleBarWidth}
                        height={barHeight}
                        fill={hist >= 0 ? '#10b981' : '#f43f5e'}
                        opacity="0.75"
                      />
                    );
                  })}

                  {/* MACD Fast Line */}
                  <polyline
                    points={candles.map((c, i) => `${getX(i)},${subPanelHeight / 2 - (c.macd || 0) * 8}`).join(' ')}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="1.2"
                  />

                  {/* MACD Signal Line */}
                  <polyline
                    points={candles.map((c, i) => `${getX(i)},${subPanelHeight / 2 - (c.macdSignal || 0) * 8}`).join(' ')}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="1.2"
                  />
                </g>
              )}
            </svg>
          </div>
        )}
      </div>

      {/* 4. FOOTER STATUS BAR */}
      <div className="bg-[#090a0f] border-t border-white/[0.06] px-3.5 py-1.5 flex flex-wrap items-center justify-between text-[10px] text-slate-400">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            SOR Venue: <strong className="text-slate-200">Ultra-FIX Direct (1.2ms)</strong>
          </span>
          <span className="text-slate-600">|</span>
          <span>Timezone: <strong className="text-slate-200">{settings.marketClockTimezone || 'UTC'}</strong></span>
          <span className="text-slate-600">|</span>
          <span>Bars: <strong className="text-slate-200">{candles.length}</strong></span>
        </div>

        <div className="flex items-center gap-2">
          {onQuickOrder && (
            <>
              <button
                onClick={() => onQuickOrder('BUY', candles[candles.length - 1]?.close || price)}
                className="px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[9px]"
              >
                Quick Buy {formatPrice(candles[candles.length - 1]?.close || price, symbol)}
              </button>
              <button
                onClick={() => onQuickOrder('SELL', candles[candles.length - 1]?.close || price)}
                className="px-2 py-0.5 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold text-[9px]"
              >
                Quick Sell {formatPrice(candles[candles.length - 1]?.close || price, symbol)}
              </button>
            </>
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

// Generate realistic synthetic OHLCV candle history
function generateCandles(_symbol: string, currentPrice: number, count: number, timeframe: TimeFrame): CandleData[] {
  const result: CandleData[] = [];
  let prevClose = currentPrice * 0.94; // start 6% lower for nice realistic uptrend

  const now = Date.now();
  const stepMs = timeframe === '1m' ? 60000 : timeframe === '5m' ? 300000 : timeframe === '15m' ? 900000 : timeframe === '1h' ? 3600000 : timeframe === '4h' ? 14400000 : 86400000;

  for (let i = count; i >= 0; i--) {
    const timestamp = now - i * stepMs;
    const date = new Date(timestamp);
    const timeStr = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;

    const drift = (currentPrice - prevClose) / (i + 1);
    const volPct = 0.008 + Math.random() * 0.006;
    const change = (Math.random() - 0.47) * currentPrice * volPct + drift;
    
    const open = prevClose;
    const close = Math.max(open * 0.85, open + change);
    const high = Math.max(open, close) + Math.random() * currentPrice * 0.004;
    const low = Math.min(open, close) - Math.random() * currentPrice * 0.004;
    const volume = Math.floor(Math.random() * 1400) + 120;

    prevClose = close;

    result.push({
      time: timeStr,
      timestamp,
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume
    });
  }

  // Ensure last candle matches real current mark price
  if (result.length > 0) {
    result[result.length - 1].close = currentPrice;
    result[result.length - 1].high = Math.max(result[result.length - 1].high, currentPrice);
    result[result.length - 1].low = Math.min(result[result.length - 1].low, currentPrice);
  }

  return calculateTechnicalIndicators(result);
}

// Compute EMA, Bollinger Bands, RSI, MACD, VWAP
function calculateTechnicalIndicators(data: CandleData[]): CandleData[] {
  let cumulativeVol = 0;
  let cumulativeVolPrice = 0;

  // EMA Multipliers
  const k20 = 2 / (20 + 1);
  const k50 = 2 / (50 + 1);
  const k200 = 2 / (200 + 1);

  let ema20 = data[0]?.close || 0;
  let ema50 = data[0]?.close || 0;
  let ema200 = data[0]?.close || 0;
  let ema12 = data[0]?.close || 0;
  let ema26 = data[0]?.close || 0;
  let macdSignal = 0;

  // RSI variables
  const rsiPeriod = 14;
  let gains = 0;
  let losses = 0;

  return data.map((c, i) => {
    // VWAP
    cumulativeVol += c.volume;
    cumulativeVolPrice += ((c.high + c.low + c.close) / 3) * c.volume;
    const vwap = cumulativeVol > 0 ? +(cumulativeVolPrice / cumulativeVol).toFixed(2) : c.close;

    // EMAs
    ema20 = i === 0 ? c.close : c.close * k20 + ema20 * (1 - k20);
    ema50 = i === 0 ? c.close : c.close * k50 + ema50 * (1 - k50);
    ema200 = i === 0 ? c.close : c.close * k200 + ema200 * (1 - k200);

    // MACD
    ema12 = i === 0 ? c.close : c.close * (2 / 13) + ema12 * (1 - 2 / 13);
    ema26 = i === 0 ? c.close : c.close * (2 / 27) + ema26 * (1 - 2 / 27);
    const macd = +(ema12 - ema26).toFixed(2);
    macdSignal = i === 0 ? macd : macd * (2 / 10) + macdSignal * (1 - 2 / 10);
    const macdHist = +(macd - macdSignal).toFixed(2);

    // Bollinger Bands (20, 2.0)
    let bbUpper = undefined;
    let bbLower = undefined;
    let bbMiddle = undefined;
    if (i >= 19) {
      const slice = data.slice(i - 19, i + 1).map(x => x.close);
      const mean = slice.reduce((a, b) => a + b, 0) / 20;
      const variance = slice.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / 20;
      const stdDev = Math.sqrt(variance);
      bbMiddle = +mean.toFixed(2);
      bbUpper = +(mean + stdDev * 2).toFixed(2);
      bbLower = +(mean - stdDev * 2).toFixed(2);
    }

    // RSI (14)
    let rsi = 50;
    if (i > 0) {
      const diff = c.close - data[i - 1].close;
      const gain = diff > 0 ? diff : 0;
      const loss = diff < 0 ? Math.abs(diff) : 0;

      if (i <= rsiPeriod) {
        gains += gain;
        losses += loss;
        if (i === rsiPeriod) {
          const avgGain = gains / rsiPeriod;
          const avgLoss = losses / rsiPeriod;
          const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
          rsi = +(100 - 100 / (1 + rs)).toFixed(1);
        }
      } else {
        const avgGain = (gains * (rsiPeriod - 1) + gain) / rsiPeriod;
        const avgLoss = (losses * (rsiPeriod - 1) + loss) / rsiPeriod;
        gains = avgGain;
        losses = avgLoss;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        rsi = +(100 - 100 / (1 + rs)).toFixed(1);
      }
    }

    return {
      ...c,
      ema20: +ema20.toFixed(2),
      ema50: +ema50.toFixed(2),
      ema200: +ema200.toFixed(2),
      bbUpper,
      bbLower,
      bbMiddle,
      vwap,
      rsi,
      macd,
      macdSignal: +macdSignal.toFixed(2),
      macdHist
    };
  });
}
