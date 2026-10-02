import React, { useState } from 'react';
import { Power, X } from 'lucide-react';
import { runControl, ControlFailure } from '../lib/control';

interface KillSwitchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmKill: () => void;
}

/**
 * Emergency kill switch. Invoking it POSTs the real `trigger_kill_switch`
 * control action (audited server-side, RBAC-gated). Denials (403/VIEWER) and
 * failures surface honestly inline — no simulated halt sequence.
 */
export const KillSwitchModal: React.FC<KillSwitchModalProps> = ({
  isOpen,
  onClose,
  onConfirmKill,
}) => {
  const [confirmationText, setConfirmationText] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!isOpen) return null;

  const isConfirmed = confirmationText.trim().toUpperCase() === 'CONFIRM HALT';

  const handleExecute = async () => {
    if (!isConfirmed || isExecuting) return;
    setIsExecuting(true);
    setActionError(null);
    try {
      await runControl("trigger_kill_switch");
      onConfirmKill();
    } catch (err) {
      const msg = err instanceof ControlFailure ? err.message : String(err);
      setActionError(
        err instanceof ControlFailure && err.kind === "denied"
          ? `Kill switch denied: ${msg} (this role may not perform trigger_kill_switch)`
          : `Kill switch failed: ${msg}`,
      );
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-surface-sunken backdrop-blur-md flex items-center justify-center p-4 animate-fade-in font-mono">
      <div className="w-full max-w-lg bg-[var(--color-surface-1)] border border-destructive rounded-lg shadow-[0_0_50px_rgba(239,68,68,0.3)] overflow-hidden flex flex-col p-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-destructive">
          <div className="flex items-center gap-2.5 text-destructive">
            <div className="w-8 h-8 rounded bg-destructive border border-destructive flex items-center justify-center">
              <Power className="w-5 h-5 text-destructive" />
            </div>
            <div>
              <h2 className="text-base font-bold text-text-strong tracking-tight">EMERGENCY KILL SWITCH</h2>
              <div className="text-[10px] text-destructive font-mono">AUDITED CONTROL ACTION: trigger_kill_switch</div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded bg-surface-veil text-text-muted hover:text-text-strong"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Warning Content */}
        <div className="my-4 space-y-3 text-xs">
          <div className="p-3 rounded bg-destructive border border-destructive text-destructive leading-relaxed">
            <strong>WARNING:</strong> Invoking the kill switch sends a real, audited
            control action to the backend. It is RBAC-gated: without an operator token
            for a permitted role the server denies it.
          </div>

          <ul className="space-y-1.5 text-text text-[11px] list-disc list-inside pl-1">
            <li>Requests cancellation of working orders and flattening via the server control plane.</li>
            <li>Transitions Autonomy Level toward <span className="text-destructive font-bold">EMERGENCY_HALT</span> server-side.</li>
            <li>Records an audited CONTROL_ACTION event in the hash chain.</li>
          </ul>

          {actionError && (
            <div className="p-2.5 rounded bg-destructive-bg border border-destructive text-destructive text-[11px] leading-relaxed">
              {actionError}
            </div>
          )}

          <div className="pt-2 border-t border-border-subtle">
            <label className="block text-[10px] text-text-muted mb-1.5 uppercase">
              Type <span className="text-destructive font-bold">CONFIRM HALT</span> to authorize emergency shutdown:
            </label>
            <input
              type="text"
              value={confirmationText}
              onChange={(e) => setConfirmationText(e.target.value)}
              placeholder="CONFIRM HALT"
              className="w-full px-3 py-2 rounded bg-surface-deep border border-destructive text-sm text-destructive placeholder-text-subtle focus:outline-none focus:border-destructive font-mono font-bold tracking-wider"
              autoFocus
            />
          </div>
        </div>

        {/* Actions */}
        <div className="pt-4 border-t border-border-strong flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded bg-surface-veil hover:bg-surface-raised text-xs text-text hover:text-text-strong transition-colors"
          >
            CANCEL & RETURN
          </button>

          <button
            onClick={handleExecute}
            disabled={!isConfirmed || isExecuting}
            className={`px-5 py-2 rounded text-xs font-bold font-mono transition-all flex items-center gap-2 ${
              isConfirmed && !isExecuting
                ? 'bg-destructive hover:bg-destructive text-text-strong shadow-[0_0_15px_rgba(239,68,68,0.5)] cursor-pointer'
                : 'bg-destructive text-destructive border border-destructive cursor-not-allowed'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            <span>{isExecuting ? 'SENDING KILL ACTION…' : 'EXECUTE EMERGENCY HALT'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
