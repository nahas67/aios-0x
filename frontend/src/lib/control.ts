/**
 * Control-plane action catalog + runner. The backend remains the sole RBAC
 * authority; these metadata exist for UX (confirmations, role hints, danger
 * styling). Every execution goes through POST /api/v1/control/{action} and is
 * audited server-side as a CONTROL_ACTION event.
 */
import { controlApi, type ControlBody } from "../api/endpoints";
import type { ControlResult } from "../api/types";
import { getIdentity, type Role } from "../stores/identity";
import { pushToast } from "../stores/toasts";

export const ROLE_LEVEL: Record<Role, number> = {
  VIEWER: 0,
  OPERATOR: 1,
  RISK_ADMIN: 2,
  ADMIN: 3,
};

export interface ActionMeta {
  label: string;
  /** Human explanation shown in the confirmation dialog. */
  describe: string;
  confirm: string;
  danger?: boolean;
  minRole: Role;
}

export const ACTIONS: Record<string, ActionMeta> = {
  pause_trading: {
    label: "Pause trading",
    describe: "Halts new execution queue processing. Open positions remain managed.",
    confirm: "Pause",
    minRole: "OPERATOR",
  },
  resume_trading: {
    label: "Resume trading",
    describe: "Resumes normal execution processing after a pause.",
    confirm: "Resume",
    minRole: "OPERATOR",
  },
  cancel_open_orders: {
    label: "Cancel open orders",
    describe: "Cancels every non-terminal order currently working at the venue.",
    confirm: "Cancel all orders",
    minRole: "OPERATOR",
  },
  freeze_symbol: {
    label: "Freeze symbol",
    describe: "Blocks all research and execution for one symbol until unfrozen.",
    confirm: "Freeze",
    minRole: "OPERATOR",
  },
  unfreeze_symbol: {
    label: "Unfreeze symbol",
    describe: "Lifts the freeze on a symbol.",
    confirm: "Unfreeze",
    minRole: "OPERATOR",
  },
  set_max_position_pct: {
    label: "Set max class exposure",
    describe: "Changes the deterministic risk governor's maximum per-class exposure percentage.",
    confirm: "Apply limit",
    minRole: "RISK_ADMIN",
  },
  set_halt_drawdown_pct: {
    label: "Set halt drawdown",
    describe: "Changes the drawdown level that triggers an emergency halt. Lower is safer.",
    confirm: "Apply halt level",
    minRole: "RISK_ADMIN",
  },
  trigger_kill_switch: {
    label: "EMERGENCY KILL SWITCH",
    describe:
      "Flattens ALL open positions at adverse prices and escalates the system to EMERGENCY_HALT. This is the last-resort control.",
    confirm: "FLATTEN EVERYTHING",
    danger: true,
    minRole: "RISK_ADMIN",
  },
  reset_lockout: {
    label: "Reset lockout",
    describe: "Clears a risk lockout after human review. Only do this when the cause is understood.",
    confirm: "Reset lockout",
    danger: true,
    minRole: "RISK_ADMIN",
  },
  approve_live_capital: {
    label: "Approve live capital",
    describe:
      "Constitutional gate: authorizes real capital deployment. Requires principal authority and is permanently audited.",
    confirm: "APPROVE LIVE CAPITAL",
    danger: true,
    minRole: "ADMIN",
  },
  promote_challenger: {
    label: "Promote challenger",
    describe: "Promotes (or rejects) a challenger trial to champion status.",
    confirm: "Promote",
    minRole: "RISK_ADMIN",
  },
  evaluate_trial: {
    label: "Evaluate trial",
    describe: "Runs champion vs challenger evaluation over identical data. Produces evidence only.",
    confirm: "Evaluate",
    minRole: "RISK_ADMIN",
  },
  promote_model: {
    label: "Promote model",
    describe: "Promotes a model version — only possible on PASS walk-forward evidence; fail-closed.",
    confirm: "Promote model",
    minRole: "RISK_ADMIN",
  },
  set_autonomy: {
    label: "Set autonomy mode",
    describe:
      "MANUAL: nothing executes. ASSISTED: research only. SUPERVISED: plans queue for your approval. AUTONOMOUS: executes within risk limits.",
    confirm: "Apply mode",
    minRole: "RISK_ADMIN",
  },
  approve_plan: {
    label: "Approve plan",
    describe: "Approves the pending allocation plan and routes it to execution.",
    confirm: "Approve",
    minRole: "RISK_ADMIN",
  },
  reject_plan: {
    label: "Reject plan",
    describe: "Rejects the pending allocation plan. It will not execute.",
    confirm: "Reject",
    danger: true,
    minRole: "RISK_ADMIN",
  },
  set_research_mode: {
    label: "Set research mode",
    describe: "'auto' uses LLM debate when configured; 'deterministic' forces template research.",
    confirm: "Apply",
    minRole: "RISK_ADMIN",
  },
};

export class ControlFailure extends Error {
  kind: "denied" | "failed";
  constructor(message: string, kind: "denied" | "failed") {
    super(message);
    this.kind = kind;
  }
}

/** Execute one audited control action as the current operator identity. */
export async function runControl(
  action: string,
  params: Record<string, string | number> = {},
): Promise<ControlResult> {
  const meta = ACTIONS[action];
  const identity = getIdentity();
  const body: ControlBody = {
    operator_id: identity.operatorId || "console",
    role: identity.role,
    params,
  };
  try {
    const result = await controlApi.execute(action, body);
    pushToast(
      "ok",
      `${meta?.label ?? action} — OK (audited)`,
      summarizeResult(result.result),
    );
    return result;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("403") || msg.toLowerCase().includes("may not perform")) {
      pushToast(
        "bad",
        "Action denied",
        `Role ${identity.role} is not authorized for ${meta?.label ?? action}. The attempt is recorded in the audit trail.`,
      );
      throw new ControlFailure(msg, "denied");
    }
    pushToast("bad", `${meta?.label ?? action} failed`, msg);
    throw new ControlFailure(msg, "failed");
  }
}

function summarizeResult(result: Record<string, unknown> | undefined): string | undefined {
  if (!result) return undefined;
  return Object.entries(result)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${typeof v === "object" ? "…" : String(v)}`)
    .join("  ");
}
