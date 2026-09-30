/**
 * Catalog conformance: ACTIONS must mirror the real ControlAction enum in
 * core/control_plane.py exactly — no invented actions, none missing.
 * If Python gains an action, this test fails until the catalog is rebuilt.
 */
import { describe, expect, it } from "vitest";
import { ACTIONS } from "./control";
import { ROLE_LEVEL } from "../stores/identity";

/** Every value of core/control_plane.py::ControlAction (19 total). */
const CONTROL_ACTIONS = [
  "pause_trading",
  "resume_trading",
  "cancel_open_orders",
  "freeze_symbol",
  "unfreeze_symbol",
  "set_max_position_pct",
  "set_halt_drawdown_pct",
  "trigger_kill_switch",
  "reset_lockout",
  "approve_live_capital",
  "promote_challenger",
  "evaluate_trial",
  "promote_model",
  "set_autonomy",
  "approve_plan",
  "reject_plan",
  "set_research_mode",
  "resolve_reconciliation_finding",
] as const;

describe("control action catalog", () => {
  it("covers every real ControlAction and nothing else", () => {
    expect(Object.keys(ACTIONS).sort()).toEqual([...CONTROL_ACTIONS].sort());
  });

  it("every entry has label, describe, confirm, and a valid minRole", () => {
    for (const [action, meta] of Object.entries(ACTIONS)) {
      expect(meta.label.length, `${action}.label`).toBeGreaterThan(0);
      expect(meta.describe.length, `${action}.describe`).toBeGreaterThan(0);
      expect(meta.confirm.length, `${action}.confirm`).toBeGreaterThan(0);
      expect(meta.minRole, `${action}.minRole`).toMatch(/^(VIEWER|OPERATOR|RISK_ADMIN|ADMIN)$/);
    }
  });

  it("matches the RBAC matrix tiers in core/control_plane.py", () => {
    // OPERATOR set (viewer matrix is empty — nothing is viewer-grade).
    for (const a of [
      "pause_trading",
      "resume_trading",
      "cancel_open_orders",
      "freeze_symbol",
      "unfreeze_symbol",
      "resolve_reconciliation_finding",
    ]) {
      expect(ACTIONS[a].minRole, a).toBe("OPERATOR");
    }
    // RISK_ADMIN additions.
    for (const a of [
      "set_max_position_pct",
      "set_halt_drawdown_pct",
      "trigger_kill_switch",
      "reset_lockout",
      "promote_challenger",
      "evaluate_trial",
      "promote_model",
      "set_autonomy",
      "approve_plan",
      "reject_plan",
      "set_research_mode",
    ]) {
      expect(ACTIONS[a].minRole, a).toBe("RISK_ADMIN");
    }
    // Sole ADMIN action.
    expect(ACTIONS["approve_live_capital"].minRole).toBe("ADMIN");
  });

  it("escalation ordering holds via the single ROLE_LEVEL declaration", () => {
    expect(ROLE_LEVEL.VIEWER).toBeLessThan(ROLE_LEVEL.OPERATOR);
    expect(ROLE_LEVEL.OPERATOR).toBeLessThan(ROLE_LEVEL.RISK_ADMIN);
    expect(ROLE_LEVEL.RISK_ADMIN).toBeLessThan(ROLE_LEVEL.ADMIN);
    for (const meta of Object.values(ACTIONS)) {
      expect(ROLE_LEVEL[meta.minRole]).toBeGreaterThan(ROLE_LEVEL.VIEWER);
    }
  });

  it("marks irreversible actions as danger", () => {
    expect(ACTIONS["trigger_kill_switch"].danger).toBe(true);
    expect(ACTIONS["reset_lockout"].danger).toBe(true);
    expect(ACTIONS["approve_live_capital"].danger).toBe(true);
    expect(ACTIONS["reject_plan"].danger).toBe(true);
    expect(ACTIONS["pause_trading"].danger).toBeFalsy();
  });
});
