# Mission OS and Manifest v1 — design

**Date:** 2026-08-08  
**Status:** operator-accepted 2026-08-08 (amended tip `f93f964`; implementation plan `docs/superpowers/plans/2026-08-08-mission-os-first-slice.md`)  
**Orchestration note:** packaging directions came from brainstorming; P1
hardening from gauntlet; operator durable assent recorded in-session 2026-08-08
(“yes”) — authoring session still must not self-accept *implementation*  
**Repo:** `practical-agency`  
**Related:** `docs/release/MANIFEST-TEETH.md`, `docs/release/VERSIONING.md`,
`docs/release/RELEASE-1.0.0-CRITERIA.md`,
`docs/release/OPERATOR-WAIVER-DEFER-0.1.0-RELEASE-2026-08-08.md`,
`docs/gauntlet-runs/mission-os-v1-design-2026-08-08/`

## Summary

Practical Agency’s v1 claim surface remains the **first operator-useful major**
(see VERSIONING / RELEASE-1.0.0-CRITERIA): authorized intent installable in
declared harnesses, advanced through ≥1 bounded adapter with an **external
durable receipt**, resumable from checkpoints, closable only by an independent
acceptor. Whether that is “worth invoking” is an adoption/falsifier question
from MANIFEST-TEETH — not established by this design prose.

This design introduces an internal **mission OS** seat that coexists with the
public **`manifest`** skill. It does **not** add a second public skill and does
**not** split a new repository at v1. Discipline routing remains outside PA:
`metacognate` and other installed member skills announce themselves. The phrase
“helix it” is legacy synonym only and must never gain special behavior.

A manual-degraded gauntlet on the brainstorming draft returned **NO-GO** until
the P1 hardening below landed in this document. The operator accepted this
amended revision on 2026-08-08; implementation follows the bound plan (not this
prose alone).

## Goals

- Carry operator intentions into durable, receipted action under bounded
  delegated agency (toward the v1 claim surface — not a tag in this design).
- Keep **one public entry skill**: `manifest`.
- Add internal **mission OS** for frontier proposals, re-plan on contradiction,
  deferred interests, and return-point hygiene — without becoming a second
  coordination driver.
- Stay **continuously flexible**: discover capability *conditions*; never ship a
  stage-to-skill inventory; never have PA select named epistemic skills.
- Park off-mission-but-valuable threads as durable **deferred interests**
  proportional to criticality; do not chase them by default; never park
  critical-path proof work.
- Escalate to the operator for escalation/protected/irreversible cases and for
  ambiguous critical-path judgments — not for routine reversible work.

## Non-goals

- A second public skill for planning, resume, defer, or routing.
- A separate mission-OS repository at v1.
- Special “helix” mode, table, or package member.
- Replacing `metacognate` or absorbing epistemic/workflow methods into PA.
- PA-owned discover→invoke that chooses skill names (soft Helix).
- General-purpose shell execution, daemon, or hosted service.
- Claiming comparative efficacy, “proven useful,” or tagging `0.1.0` as part of
  this design (operator waived immediate release review).
- Treating a fixture e2e slice as field v1 / RELEASE-1.0.0 world-power.

## Architecture

| Concept | Form | Owns |
| --- | --- | --- |
| Mission steward | Public skill `manifest` + deterministic kernel | Intent custody, authority allowlists, live re-anchor, one bounded dispatch, adapters, never self-certify; **sole writer** of durable mission state under revision/checkpoint rules |
| Mission OS | Internal module + contract + role (not a skill) | **Proposes** frontier patches, re-plan slices, deferrals, return-point hygiene; never authorizes dispatch; never sole-writes the durable frontier |
| Epistemic / workflow disciplines | External installed skills (examples in prose only) | Their own triggers, methods, verdicts; return control when done |

**Packaging decision (locked):** mission OS lives **in** `practical-agency`.
Extract to another repo only after at least two independent consumers need a
separately versioned component or release cadence clearly diverges.

**Legacy phrase (locked):** `"helix it"` normalizes to the same invocation intent
as `"manifest this"` / `"carry this through"`. No unique functionality ever.
Oracle: behavioral equivalence tests, not description prose alone.

**Single coordination driver (locked):** `coordinate_once` / steward remains the
only path that may apply OS proposals and sequence dispatch. Mission OS is a
pure helper (proposal in → proposal out). Dual writers of
`state.current_frontier` in one turn are a defect.

## Mission OS

### Working identity

- Internal id: `mission-os`
- Human phrase: “mission OS”
- Not a skill directory; not a resident description budget consumer

### Jobs

1. **Frontier propose** — emit an ordered patch of bounded next-step **labels**
   (conditions/outcomes — never skill names) targeting the sole durable carrier
   `state.current_frontier`.
2. **Re-plan propose** — when reconciliation or results invalidate the frontier,
   propose rewrite of only the affected slice; never invent new operator ends.
3. **Defer propose** — if a thread is valuable and **provably not required** for
   unmet `completion_proof` / `scope_proof` / desired state, emit
   `deferred-interest@1` and keep the frontier on mission-critical work.
4. **Return hygiene** — every side engagement carries exact return point:
   `mission_id`, `revision`, `frontier_index`, `label` (aligned with live
   `ReturnPoint`). Re-plan that changes index/label binding must invalidate or
   explicitly rebind open return points — never soft-land.

### Must not

- Maintain a skill-name inventory or stage-to-skill table (static or soft-dynamic).
- Select or invoke a named epistemic/workflow skill (emit condition + return only).
- Authorize dispatch or grant permissions.
- Apply its own proposals to the durable manifest (steward/kernel applies).
- Perform world effects (adapters under steward authority).
- Certify mission completion.
- Chase deferred interests unless the operator (or authority-gated absorb) brings
  them in.
- Alter `authority.instruction` or `outcome.desired_state` (or listed proof
  fields) under “re-plan.”

### Proposal / apply contract (P1)

Mission OS outputs a typed proposal, e.g.:

- `frontier_patch` — replace/reorder slice of `state.current_frontier`
- `replan_slice` — contradiction-driven patch with cited truth markers
- `defer` — `deferred-interest@1` object + frontier unchanged for critical items
- `return_rebind` — invalidate/rebind open return points after frontier change

Steward/kernel **apply** is a recorded event on the mission revision path
(checkpointed). Dispatch or capability interrupt may use a frontier/`next_action`
only after that apply. OS output used without apply is illegal.

### Re-plan constraints (P1)

Allowed to change: `state.current_frontier`, `state.next_action` (via apply),
`state.blockers`, and truth reopen markers (`contradictions` / `unknowns`) as
required by live reconcile.

Forbidden without append-only authority amendment: any byte change to
`authority.instruction`, `outcome.desired_state`, or removing/weakening
`completion_proof` / `integrity_guards` / `scope_proof` / `stop_conditions`.

Frontier labels must be entailed by instruction, amendments, desired state, or
live contradictions — not novel aims. `suggested_next` on a deferred interest is
a non-binding hint and cannot expand ends on absorb.

### Defer constraints (P1)

- Refuse defer when the candidate is necessary for any unmet
  `completion_proof` / `scope_proof` item, or is the sole open path to desired
  state.
- If necessity is ambiguous → keep on frontier or escalate; do not “optimistically”
  park.
- `criticality`: steward/operator-set or closed rule; `high` requires nonempty
  `subject_refs`. Under-classifying work that touches protected state or
  completion-proof subjects to avoid gates is a defect.

### Absorb constraints (P1)

- `criticality=high` absorb (`open` → `absorbed`) requires an operator authority
  event: append-only amendment and/or explicit absorb approval naming effects,
  permissions, and costs as needed.
- Mission OS must not insert absorb steps onto the frontier to self-serve re-entry.
- Medium/low absorb may proceed via explicit frontier absorb apply under steward
  rules without inventing ends (still subject to re-plan constraints).

## Deferred interest contract (`deferred-interest@1`)

Minimum fields:

| Field | Meaning |
| --- | --- |
| `schema` | `deferred-interest@1` |
| `mission_id` | Owning mission |
| `summary` | One-line description |
| `criticality` | `low` \| `medium` \| `high` |
| `why_not_now` | Why it is not on the critical path |
| `suggested_next` | Optional non-binding hint; must not expand ends |
| `subject_refs` | Optional list; required when `criticality` is `high` |
| `created_at_revision` | Mission revision when parked |
| `status` | `open` \| `absorbed` \| `discarded` |

**Proportionality:** low → one line; medium → short rationale; high → rationale
plus `subject_refs`.

**Schema evolution (locked for impl plan):** additive optional
`continuity.deferred_interests` under still-`mission-manifest@1`, default `[]`,
old checkpoints migrate on read; `additionalProperties` stays false with the new
property listed. Do not claim durability until schema + validator accept the
field. (Epoch bump only if additive path is later rejected — not the default.)

## Control flow (one coordination turn)

```text
operator intent
  → manifest (create / resume / reconcile)  # internal ops, not separate public skills
  → mission OS propose (frontier / re-plan / defer / return hygiene)
  → steward/kernel APPLY proposal (revision + checkpoint path)
  → smallest blocker to justified progress
       ├─ unanswerable condition (discipline needed)?
       │     → emit condition + exact return point
       │     → external seat (e.g. metacognate / installed skill) selects/runs
       │     → return to exact ReturnPoint (index + label)
       ├─ authorized world effect needed?
       │     → adapter dispatch + external durable receipt
       │     → observe + checkpoint
       └─ off-mission but valuable AND not critical-path?
             → defer proposal → apply; stay on critical frontier
  → checkpoint
  → repeat until verifying → independent acceptor
```

Iron turn rules:

- At most one consequential dispatch **or** one capability interrupt per turn.
- Checkpoint + live reconcile outrank chat/memory.
- Missing skill/adapter → degraded / `BLOCKED`, not improvisation.
- Operator re-ask for escalation, protected state, irreversible/material danger,
  or ambiguous critical-path / high-absorb decisions.

## Relationship to existing seats

| Seat | Relationship |
| --- | --- |
| `manifest` | Sole public entry; remains mission steward and apply authority |
| `coordinate_once` / kernel | Sole coordination driver; applies OS proposals; dispatches |
| `state.current_frontier` | Sole durable frontier carrier |
| `FilesystemArtifactAdapter` | Example world-power adapter; not v1 by itself |
| External disciplines | Own routing/methods; PA does not inventory them |
| `write-goal` | Completion-contract authoring when explicitly requested — not mission custody |
| `decision-ledger` | Persist consequential decisions — not frontier planning |
| `"helix it"` | Legacy synonym only |

## Degradation

| Missing | Required behavior |
| --- | --- |
| No epistemic/workflow package | Routine directly checkable work only; mark unavailable gates |
| No execution adapter | Preserve mission; `BLOCKED`; no prose substitute |
| No durable store | Session-bounded; state that resumption is unavailable |
| No independent acceptor | May enter `verifying`; never `completed` for material work |
| Tempting off-path thread | Deferred interest (if not critical-path) or explicit mission-critical justification |
| Schema without `deferred_interests` | Must not claim durable defer; refuse or migrate first |

## Testing strategy

Deterministic tests (RED → GREEN → REFACTOR) must cover:

1. Frontier re-plan after live-state contradiction (no ends invented).
2. Deferred interest created while critical frontier unchanged; refuse defer of
   completion-proof-necessary work.
3. Capability interrupt restores exact `ReturnPoint` (index + label); re-plan
   invalidates stale returns.
4. OS proposal without apply cannot justify dispatch.
5. High absorb without authority event refused.
6. Receipted adapter effect survives crash/reload from checkpoint.
7. Steward self-acceptance refused.
8. No skill-name inventory / stage→skill map in mission OS or `manifest`.
9. `"helix it"` ≡ `"manifest this"` semantics.
10. Fixture slice labeled NOT CLAIMED for RELEASE-1.0.0 world-power.

## First implementation slice (after plan)

Build a realistic mission proof path (fixture and/or documented run):

create → approve → OS propose + apply frontier → optional deferred distraction
(non-critical) → receipted filesystem write → discard in-memory state → resume
from checkpoint → reconcile → verifying → independent accept — with original
operator instruction unchanged.

**Claim ceiling for this slice:** advances custody/continuity machinery toward
v1 teeth. It is **not** a release tag and **does not** by itself satisfy
RELEASE-1.0.0 world-power, live harness, or “proven useful.”

## Success criteria for this design

The **amended** design is accepted when:

1. Operator agrees (durable assent) that mission OS is internal-in-repo, not a
   second public skill, and accepts the P1 hardening in this revision.
2. Discipline routing remains outside PA inventories (condition+return only).
3. Deferred interests, sole frontier carrier, proposal/apply, re-plan/defer/absorb
   constraints, and return-point index rules are specified enough to implement
   without inventing ends or durability theater.
4. “helix it” special behavior is explicitly forbidden with a behavioral oracle.
5. First build slice is small enough for one implementation plan and explicitly
   fixture≠field-v1.
6. Gauntlet P1 conditions in
   `docs/gauntlet-runs/mission-os-v1-design-2026-08-08/ARBITRATION.md` are
   addressed in this text (re-score after amend).

Authoring-session checklist alone is not acceptance.

## Open follow-ups (explicitly later)

- Whether deferred interests ever need an independent public trigger (default: no).
- Multi-adapter world paths beyond filesystem text artifacts.
- Comparative evaluation vs ordinary skilled agents.
- Repo extraction of mission OS after multiple consumers exist.
- Full independence gauntlet (registry selector + isolated role-agents +
  cross-family judge) on the implementation tip — this design review was
  `manual-degraded`.

## Epistemic record

| Item | Value |
| --- | --- |
| Metacognate | Fired — design approval is high-blast / architecture commit |
| Gauntlet | `docs/gauntlet-runs/mission-os-v1-design-2026-08-08/` |
| Unamended verdict | **NO-GO** |
| Amended tip | `f93f964` — design accept bound to implementation plan tip |
| Operator accept | yes — chat 2026-08-08 (amended design) |
| Implementation plan | `docs/superpowers/plans/2026-08-08-mission-os-first-slice.md` |
