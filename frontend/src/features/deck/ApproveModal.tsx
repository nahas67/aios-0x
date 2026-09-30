/**
 * Confirmation modal for control-plane actions. Shows the human-readable
 * consequence, requires explicit confirm, then executes through the audited
 * backend endpoint as the current operator identity.
 */
import { useState, type ReactNode } from "react";
import { runControl, type ActionMeta } from "../../lib/control";
import { Modal } from "../../components/ui";
import { getIdentity, ROLE_LEVEL } from "../../stores/identity";

export function ApproveModal({
  action,
  meta,
  onClose,
  onDone,
  renderBody,
  extraParams,
}: {
  action: string;
  meta: ActionMeta | undefined;
  onClose: () => void;
  onDone?: () => void;
  renderBody?: (meta: ActionMeta | undefined) => ReactNode;
  extraParams?: Record<string, string | number>;
}) {
  const [busy, setBusy] = useState(false);
  const identity = getIdentity();

  const confirm = async () => {
    if (!meta || busy) return;
    setBusy(true);
    try {
      await runControl(action, extraParams ?? {});
      onDone?.();
      onClose();
    } catch {
      // toast already emitted by runControl
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const underleveled = ROLE_LEVEL[identity.role] < ROLE_LEVEL[meta?.minRole ?? "ADMIN"];

  return (
    <Modal title={meta?.label ?? action} onClose={onClose}>
      {renderBody ? (
        renderBody(meta)
      ) : (
        <p>{meta?.describe}</p>
      )}
      {underleveled && (
        <p style={{ color: "var(--warn)", fontWeight: 600 }}>
          Your role {identity.role} is below the required {meta?.minRole}. The backend will deny this action — and the denial is audited.
        </p>
      )}
      <div className="row">
        <button className="btn" onClick={onClose} type="button" disabled={busy}>
          Cancel
        </button>
        <button className={`btn ${meta?.danger ? "danger" : "primary"}`} onClick={confirm} type="button" disabled={busy}>
          {busy ? "Executing…" : (meta?.confirm ?? "Confirm")}
        </button>
      </div>
    </Modal>
  );
}
