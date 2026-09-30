# AIOS-0X Goal Registry (G010–G280)

Machine-readable source of the vNext goal identifiers used by
`C:\Users\nahas\OneDrive\Desktop\ARCHITECTURE.txt` §13 and enforced by
`tests/test_goal_registry.py`.

Before this registry existed, no `G0xx` token appeared in any document in this
repository. Goals were described in prose, so "is G040 done?" had no
authoritative answer. The registry makes each goal a queryable object with a
status, a set of gates, and a pointer to the evidence that closes it.

## Authority

The registry is the single source of truth for goal **status**. Where it
disagrees with a narrative document, the registry wins. Where it disagrees with
code, the **tests** win — a goal is `LANDED` only when its gates are enforced by
a passing test, not when a document asserts it.

Status vocabulary:

| Status | Meaning |
|---|---|
| `LANDED` | Implemented, and at least one gate is enforced by a passing test. |
| `PARTIAL` | Implemented in some form, but the goal's full gate set is not met. |
| `NOT_STARTED` | No implementation exists. |
| `BLOCKED` | Cannot proceed; `blocked_by` names the reason. |
| `SUPERSEDED` | Replaced by another goal; `superseded_by` names it. |

A goal with no status is not a goal.

## Gate semantics

A gate is a machine-checkable statement. Each carries a `check` naming the
mechanism that enforces it:

- `test:<path>` — a pytest test asserts it.
- `lint:<path>` — a build-gate script asserts it.
- `constitution` — enforced by the ratified `CONSTITUTION.md` and its SHA-256 pin.
- `manual` — requires a human signature recorded in the ADR. Never sufficient on
  its own for `LANDED`; must be paired with at least one automated check.

## Registering a new goal

Add an entry to `goals.yaml`, then update `tests/test_goal_registry.py` only if
you introduce a new status or a new `check` scheme. The validator rejects
unknown keys, duplicate ids, gates with no `check`, and `LANDED` goals whose
evidence is empty.

## Checkpoint

docs/goals/CHECKPOINT.md is a human-readable summary of where the vNext
program stands: what landed, what remains per goal, the defects found, and the
recommended next step. It is a summary, not an authority — the registry and its
tests win where they disagree.

## Read this next

`docs/12_ai_constitution.md` for the authority boundaries these goals must not
cross, and `ARCHITECTURE_PLANES.md` for the module → plane mapping each goal's
code must respect.
