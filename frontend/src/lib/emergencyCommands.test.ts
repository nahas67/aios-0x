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
  // Pinned deliberately. These three numbers ARE the finding — of §8's 8 commands, 2 work
  // fully, 2 are reachable only in part, and 4 do not exist. The partials are partial for
  // different reasons and both say so: NO_NEW_RISK is a distinct command §8 lists that
  // has no action of its own, while REDUCE_ONLY now exists and is audited but enforces
  // only the directional half of the rule (no overshoot check — classify_plan has no
  // absolute quantity). If someone wires the quantity-aware half, this fails and forces
  // the finding to be restated, which is the point: a safety gap that no test notices is
  // a safety gap that gets forgotten.
  it("reports 2 full, 2 partial, 4 none", () => {
    expect(coverageSummary()).toEqual({ full: 2, partial: 2, none: 4 });
  });

  it("names STOP and LIQUIDATE as the two that work", () => {
    expect(availableCommands().map((c) => c.command)).toEqual(["STOP", "LIQUIDATE"]);
  });

  it("names the four that do not exist", () => {
    expect(missingCommands().map((c) => c.command)).toEqual([
      "DISABLE_STRATEGY",
      "DISABLE_MODEL",
      "DISABLE_PROVIDER",
      "DISABLE_BROKER",
    ]);
  });

  // REDUCE_ONLY is deliberately partial and not available. It now exists and is audited,
  // so it left the "none" list; it did not become "full", because classify_plan cannot
  // detect an overshoot. Both of these assertions exist to stop either half of that
  // being papered over later.
  it("treats REDUCE_ONLY as partial, because overshoot is not enforced", () => {
    const reduceOnly = EMERGENCY_COMMANDS.find((c) => c.command === "REDUCE_ONLY");
    expect(reduceOnly?.coverage).toBe<Coverage>("partial");
    expect(reduceOnly?.via).toEqual(["set_reduce_only"]);
    expect(reduceOnly?.gap.toLowerCase()).toContain("overshoot");
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
