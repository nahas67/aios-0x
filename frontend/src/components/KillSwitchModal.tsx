import React, { useState } from 'react';
import {  Power, X } from 'lucide-react';

interface KillSwitchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmKill: () => void;
}

export const KillSwitchModal: React.FC<KillSwitchModalProps> = ({
  isOpen,
  onClose,
  onConfirmKill,
}) => {
  const [confirmationText, setConfirmationText] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);

  if (!isOpen) return null;

  const isConfirmed = confirmationText.trim().toUpperCase() === 'CONFIRM HALT';

  const handleExecute = () => {
    if (!isConfirmed) return;
    setIsExecuting(true);
    setTimeout(() => {
      setIsExecuting(false);
      onConfirmKill();
    }, 1200);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/85 backdrop-blur-md flex items-center justify-center p-4 animate-fade-in font-mono">
      <div className="w-full max-w-lg bg-[#0d0f17] border border-red-700/60 rounded-lg shadow-[0_0_50px_rgba(239,68,68,0.3)] overflow-hidden flex flex-col p-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-red-800/40">
          <div className="flex items-center gap-2.5 text-red-400">
            <div className="w-8 h-8 rounded bg-red-950/80 border border-red-700/60 flex items-center justify-center">
              <Power className="w-5 h-5 text-red-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">EMERGENCY KILL SWITCH</h2>
              <div className="text-[10px] text-red-400 font-mono">AUTONOMOUS DE-RISKING & HALT SEQUENCE</div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded bg-white/[0.04] text-slate-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Warning Content */}
        <div className="my-4 space-y-3 text-xs">
          <div className="p-3 rounded bg-red-950/30 border border-red-800/50 text-red-200 leading-relaxed">
            <strong>WARNING:</strong> Invoking the institutional Kill Switch initiates an irreversible automated safety sequence:
          </div>

          <ul className="space-y-1.5 text-slate-300 text-[11px] list-disc list-inside pl-1">
            <li>Cancels all 12 open limit & TWAP algorithmic slicing orders immediately.</li>
            <li>Submits market flattening orders across all connected institutional venues (Binance, CME, Hyperliquid).</li>
            <li>Transitions Autonomy Level from <span className="text-cyan-300 font-bold">SUPERVISED</span> to <span className="text-red-400 font-bold">EMERGENCY_HALT</span>.</li>
            <li>Records an immutable, non-repudiable emergency incident report to the Merkle audit trail.</li>
          </ul>

          <div className="pt-2 border-t border-white/[0.06]">
            <label className="block text-[10px] text-slate-400 mb-1.5 uppercase">
              Type <span className="text-red-400 font-bold">CONFIRM HALT</span> to authorize emergency shutdown:
            </label>
            <input
              type="text"
              value={confirmationText}
              onChange={(e) => setConfirmationText(e.target.value)}
              placeholder="CONFIRM HALT"
              className="w-full px-3 py-2 rounded bg-black/60 border border-red-800/60 text-sm text-red-300 placeholder-slate-600 focus:outline-none focus:border-red-500 font-mono font-bold tracking-wider"
              autoFocus
            />
          </div>
        </div>

        {/* Actions */}
        <div className="pt-4 border-t border-white/[0.08] flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded bg-white/[0.04] hover:bg-white/[0.08] text-xs text-slate-300 hover:text-white transition-colors"
          >
            CANCEL & RETURN
          </button>

          <button
            onClick={handleExecute}
            disabled={!isConfirmed || isExecuting}
            className={`px-5 py-2 rounded text-xs font-bold font-mono transition-all flex items-center gap-2 ${
              isConfirmed && !isExecuting
                ? 'bg-red-600 hover:bg-red-500 text-white shadow-[0_0_15px_rgba(239,68,68,0.5)] cursor-pointer'
                : 'bg-red-950/40 text-red-800 border border-red-950 cursor-not-allowed'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            <span>{isExecuting ? 'EXECUTING HALT SEQUENCE...' : 'EXECUTE EMERGENCY HALT'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
