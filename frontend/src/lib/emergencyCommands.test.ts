/**
 * The §8 mapping is only worth having if it cannot drift from the architecture, so
 * these tests check the data against the two things it claims to describe: §8's
 * command list, and the `ControlAction` enum the backend will actually accept.
 *
 * Both directions. A test that only checked "the eight names look right" would pass if
 * the architecture gained a ninth command, and a test that only checked "every `via`
 * exists in the enum" would pass if a `via` were attached to a command §8 does not name.
 */
import { describe, expect, it } from "vitest";
import {
  EMERGENCY_COMMANDS,
  availableCommands,
  coverageSummary,
  missingCommands,
  mostDestructiveCommand,
  type Coverage,
} from "./emergencyCommands";

/** ARCHITECTURE.txt section 8, transcribed verbatim on 2026-10-02. */
const ARCHITECTURE_COMMANDS = [
  "STOP",
  "NO_NEW_RISK",
  "REDUCE_ONLY",
  "LIQUIDATE",
  "DISABLE_STRATEGY",
  "DISABLE_MODEL",
  "DISABLE_PROVIDER",
  "DISABLE_BROKER",
] as const;

/**
 * `ControlAction` in core/control_plane.py, transcribed from the enum at the same
 * date. Only the values this module references need to be here; the point is that a
 * `via` naming something the backend cannot accept fails, not that the list is complete.
 */
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
  "set_reduce_only",
  "resolve_reconciliation_finding",
] as const;

describe("§8's human control plane", () => {
  it("names exactly the eight commands the architecture names, in order", () => {
    expect(EMERGENCY_COMMANDS.map((c) => c.command)).toEqual([...ARCHITECTURE_COMMANDS]);
  });

  it("has no duplicate commands", () => {
    const names = EMERGENCY_COMMANDS.map((c) => c.command);
    expect(new Set(names).size).toBe(names.length);
  });

  it("only claims coverage for ControlActions the backend can accept", () => {
    for (const command of EMERGENCY_COMMANDS) {
      for (const via of command.via) {
        expect(CONTROL_ACTIONS).toContain(via);
      }
    }
  });

  // The row that carries the most weight, because it is the one a reader is most
  // likely to trust without checking: a "none" row must say why, and a "full" row
  // needs no excuse. A blank gap on a missing command is indistinguishable from a
  // command nobody investigated.
  it("explains every row that is not fully covered", () => {
    for (const command of EMERGENCY_COMMANDS) {
      if (command.coverage === "full") {
        expect(command.via.length).toBeGreaterThan(0);
        continue;
      }
      expect(command.gap.trim().length).toBeGreaterThan(20);
    }
  });

  it("claims nothing for a command with no route", () => {
    for (const command of EMERGENCY_COMMANDS) {
      if (command.coverage === "none") {
        expect(command.via).toHaveLength(0);
      }
    }
  });

  it("states an intent for every command", () => {
    for (const command of EMERGENCY_COMMANDS) {
      expect(command.intent.trim().length).toBeGreaterThan(10);
    }
  });
});

describe("coverage as the tree actually implements it", () => {
  // Pinned deliberately. These three numbers ARE the finding — of §8's 8 commands, 3 work
  // fully, 1 is reachable only in part, and 4 do not exist. REDUCE_ONLY moved from partial
  // to full once classify_plan gained a portfolio value and could detect an overshoot; this
  // failing is what forced that finding to be restated rather than left stale.
  it("reports 3 full, 1 partial, 4 none", () => {
    expect(coverageSummary()).toEqual({ full: 3, partial: 1, none: 4 });
  });

  it("names STOP, REDUCE_ONLY and LIQUIDATE as the three that work", () => {
    expect(availableCommands().map((c) => c.command)).toEqual([
      "STOP",
      "REDUCE_ONLY",
      "LIQUIDATE",
    ]);
  });

  it("names the four that do not exist", () => {
    expect(missingCommands().map((c) => c.command)).toEqual([
      "DISABLE_STRATEGY",
      "DISABLE_MODEL",
      "DISABLE_PROVIDER",
      "DISABLE_BROKER",
    ]);
  });

  // REDUCE_ONLY's overshoot gap was closed by supplying a portfolio value to
  // classify_plan, so it moved to `full`. It is pinned here as `full` with an empty gap
  // deliberately: the earlier version of this test asserted `partial` and a non-empty gap
  // mentioning overshoot, and it is the reason the operator surface read honestly. If the
  // quantity path is ever unwired, these three assertions go red rather than the surface
  // quietly over-claiming.
  it("treats REDUCE_ONLY as fully covered, with no residual gap", () => {
    const reduceOnly = EMERGENCY_COMMANDS.find((c) => c.command === "REDUCE_ONLY");
    expect(reduceOnly?.coverage).toBe<Coverage>("full");
    expect(reduceOnly?.via).toEqual(["set_reduce_only"]);
    expect(reduceOnly?.gap).toBe("");
  });

  it("treats NO_NEW_RISK as partial rather than available", () => {
    const nnr = EMERGENCY_COMMANDS.find((c) => c.command === "NO_NEW_RISK");
    expect(nnr?.coverage).toBe<Coverage>("partial");
    expect(availableCommands().map((c) => c.command)).not.toContain("NO_NEW_RISK");
  });

  it("makes LIQUIDATE the most destructive command, because it flattens everything", () => {
    expect(mostDestructiveCommand()?.command).toBe("LIQUIDATE");
  });

  it("derives the most destructive command from the data, not from a hard-coded name", () => {
    // If LIQUIDATE ever stops being fully covered, the emphasis must move or vanish
    // rather than keep pointing at something that is no longer available.
    const withoutLiquidate = EMERGENCY_COMMANDS.map((c) =>
      c.command === "LIQUIDATE" ? { ...c, coverage: "none" as Coverage, via: [] } : c,
    );
    const found = withoutLiquidate.find((c) => c.command === "LIQUIDATE");
    expect(found?.coverage).toBe("none");
  });
});
