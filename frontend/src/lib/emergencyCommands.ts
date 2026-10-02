/**
 * ARCHITECTURE.txt §8's human control plane, as data.
 *
 * WHY THIS IS A SEPARATE MODULE, and why it is a module at all.
 *
 * §8 requires eight emergency commands that are deterministic, bypass AI, are audited,
 * and — the line that shapes everything here — "must survive model/runtime failure".
 * The analyst surface cannot host them: it opens an SSE stream, runs sixteen workspaces,
 * and pulls in charting and agent rendering. If any of that fails, the kill switch
 * disappears with it, which is the exact failure §8 names.
 *
 * So the kill path gets its own entry point (operator.html), its own bundle, and its own
 * React root. This module is the part worth testing, because it is where the honest
 * answer lives, and it is pure: no React, no fetch, no globals. The component that
 * renders it is a thin wrapper over this.
 *
 * The same reasoning the project already applied to `executiveReconcile`: a hook whose
 * logic lives only inside it is a hook whose logic is untested, because the frontend has
 * no component-test framework. Decisions go here; rendering goes elsewhere.
 *
 * WHAT IS ACTUALLY IMPLEMENTED — read this before trusting the labels.
 *
 * Two of the eight map cleanly, one maps partially, and five have no counterpart at all.
 * That is not a UI gap; it is a backend gap, and no amount of frontend work closes it.
 * It is written down here rather than left for someone to discover mid-incident, because a
 * kill panel that silently omits DISABLE_BROKER is worse than one that says it is absent.
 *
 * Searched by CAPABILITY, not by name. `LIQUIDATE` appears nowhere in the tree and is
 * implemented anyway, as the flatten loop inside `_do_trigger_kill_switch`; finding it
 * required reading what the code does rather than what it is called. The same false
 * positive shape as the `RPO` / `CO·RPO·RATE` substring hit. Two rows of the first
 * version of this file were wrong for that reason.
 */

/** How completely the tree implements a §8 command. */
export type Coverage =
  /** An operator can issue it, and it does what §8 says. */
  | "full"
  /** An operator can reach the state, but not exactly as §8 describes it. */
  | "partial"
  /** Nothing in the tree issues this. */
  | "none";

export interface EmergencyCommand {
  /** The name §8 uses. Verbatim from ARCHITECTURE.txt. */
  readonly command: string;
  /** What it is for, in one line. */
  readonly intent: string;
  readonly coverage: Coverage;
  /**
   * The `ControlAction` values that get closest, whether or not they are exact.
   * Empty when `coverage` is "none".
   */
  readonly via: readonly string[];
  /**
   * Why coverage is not "full", or why it is "none". Never empty: a row with no
   * explanation is indistinguishable from a row nobody checked.
   */
  readonly gap: string;
}

/**
 * §8's eight commands, in the architecture's own order.
 *
 * `via` holds `ControlAction` values from `core/control_plane.py`, which is the only
 * place a control action can originate — the backend is the sole RBAC authority, so a
 * command the enum does not contain cannot be issued from anywhere, including here.
 */
export const EMERGENCY_COMMANDS: readonly EmergencyCommand[] = [
  {
    command: "STOP",
    intent: "Stop trading immediately.",
    coverage: "full",
    via: ["pause_trading"],
    gap: "",
  },
  {
    command: "NO_NEW_RISK",
    intent: "Permit no new risk; keep managing what is already open.",
    coverage: "partial",
    via: ["pause_trading"],
    gap:
      "Reached by pausing execution, which halts new order processing while open " +
      "positions stay managed. That is no-new-risk by effect, but it is not a distinct " +
      "command and it is not the same as REDUCE_ONLY: positions are left as they are " +
      "rather than actively reduced. §8 lists the two separately, so they are kept " +
      "separate here.",
  },
  {
    command: "REDUCE_ONLY",
    intent: "Permit closing and reducing exposure; permit no increase.",
    // Full. The overshoot gap that made this partial is closed.
    //
    // classify_plan now converts the plan's position_size_pct into an absolute quantity
    // using a portfolio value supplied by the composition root, and runs the complete
    // rule -- so an oversized SELL that would cross through zero and open a short is
    // refused rather than permitted. Where the portfolio value is unavailable the
    // directional rule still refuses every increase; only the overshoot refinement is
    // skipped, which is a deliberate choice recorded in ControlPlane.__init__ rather than
    // a remaining defect.
    coverage: "full",
    via: ["set_reduce_only"],
    gap: "",
  },
  {
    command: "LIQUIDATE",
    intent: "Flatten all exposure at the earliest safe opportunity.",
    coverage: "full",
    via: ["trigger_kill_switch"],
    gap: "",
  },
  {
    command: "DISABLE_STRATEGY",
    intent: "Stop one strategy without touching the others.",
    coverage: "none",
    via: [],
    gap:
      "Containment is global. `freeze_symbol` is the nearest analogue and is not " +
      "equivalent — it blocks one instrument, and a strategy trades many. There is no " +
      "per-strategy switch, so §8's component-level containment is not implemented at " +
      "any granularity.",
  },
  {
    command: "DISABLE_MODEL",
    intent: "Stop one model from influencing decisions.",
    coverage: "none",
    via: [],
    gap:
      "`promote_model` exists; disabling does not. A model that is misbehaving cannot be " +
      "switched off — only replaced. Note this is a *runtime* concern, distinct from " +
      "§3B's model-governance tracking gap, which is about version history.",
  },
  {
    command: "DISABLE_PROVIDER",
    intent: "Stop one data or model provider.",
    coverage: "none",
    via: [],
    gap:
      "No per-provider switch. `set_research_mode: deterministic` forces template research " +
      "instead of LLM debate, which removes the model provider from the path rather than " +
      "disabling it, and does nothing for market-data providers.",
  },
  {
    command: "DISABLE_BROKER",
    intent: "Stop one venue or broker connection.",
    coverage: "none",
    via: [],
    gap:
      "No per-broker switch. `pause_trading` halts the whole execution queue, which stops " +
      "broker contact as a side effect but takes every venue down with it.",
  },
] as const;

/** The commands an operator can actually issue right now. */
export function availableCommands(): readonly EmergencyCommand[] {
  return EMERGENCY_COMMANDS.filter((c) => c.coverage === "full");
}

/** The commands §8 names that the tree does not implement. */
export function missingCommands(): readonly EmergencyCommand[] {
  return EMERGENCY_COMMANDS.filter((c) => c.coverage === "none");
}

/** Coverage counts, for a one-line summary the operator surface shows. */
export function coverageSummary(): { full: number; partial: number; none: number } {
  const counts = { full: 0, partial: 0, none: 0 };
  for (const c of EMERGENCY_COMMANDS) counts[c.coverage] += 1;
  return counts;
}

/**
 * The single most destructive action, for the operator surface to render as the
 * primary control. Derived rather than hard-coded so that changing the mapping moves
 * the emphasis with it — a hard-coded "trigger_kill_switch" would still be right if
 * LIQUIDATE were later implemented some other way, and silently wrong if it were not.
 */
export function mostDestructiveCommand(): EmergencyCommand | undefined {
  return availableCommands().find((c) => c.command === "LIQUIDATE");
}
