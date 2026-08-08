# Mission OS and Manifest v1 — design

**Date:** 2026-08-08  
**Status:** drafted for operator review (brainstorming)  
**Repo:** `practical-agency`  
**Related:** `docs/release/MANIFEST-TEETH.md`, `docs/release/VERSIONING.md`,
`docs/release/RELEASE-1.0.0-CRITERIA.md`,
`docs/release/OPERATOR-WAIVER-DEFER-0.1.0-RELEASE-2026-08-08.md`

## Summary

Practical Agency’s v1 bar is **worth the investment**: the steward can carry
operator intent into durable, receipted action in code, survive interruption,
pull in the right external discipline mid-flight, return to the mission, and
refuse rabbit holes and self-certification — without treating any single harness
(e.g. Cursor) as the product.

This design introduces an internal **mission OS** seat that coexists with the
public **`manifest`** skill. It does **not** add a second public skill and does
**not** split a new repository at v1. Discipline routing remains with
`metacognate` and other installed member skills. The phrase “helix it” is legacy
synonym only and must never gain special behavior.

## Goals

- Make operator intentions **manifest in code** under bounded delegated agency.
- Keep **one public entry skill**: `manifest`.
- Add internal **mission OS** for frontier maintenance, re-plan, deferred
  interests, and exact return points.
- Stay **continuously flexible**: discover capabilities; never ship a
  stage-to-skill inventory.
- Park off-mission-but-valuable threads as durable **deferred interests**
  proportional to criticality; do not chase them by default.
- Escalate to the operator only for escalation/protected/irreversible cases — not
  for routine reversible work.

## Non-goals

- A second public skill for planning, resume, defer, or routing.
- A separate mission-OS repository at v1.
- Special “helix” mode, table, or package member.
- Replacing `metacognate` or absorbing epistemic/workflow methods.
- General-purpose shell execution, daemon, or hosted service.
- Claiming comparative efficacy or tagging `0.1.0` as part of this design
  (operator waived immediate release review).

## Architecture

| Concept | Form | Owns |
| --- | --- | --- |
| Mission steward | Public skill `manifest` + deterministic kernel | Intent custody, authority allowlists, live re-anchor, one bounded dispatch, adapters, never self-certify |
| Mission OS | Internal module + contract + role (not a skill) | Living frontier, re-plan on contradiction, deferred interests, return-point hygiene |
| Epistemic / workflow disciplines | External installed skills (e.g. metacognate, brainstorming, systematic-debugging, recon, resolve) | Their own triggers, methods, verdicts; return control when done |

**Packaging decision (locked):** mission OS lives **in** `practical-agency`.
Extract to another repo only after at least two independent consumers need a
separately versioned component or release cadence clearly diverges.

**Legacy phrase (locked):** `"helix it"` normalizes to the same invocation intent
as `"manifest this"` / `"carry this through"`. No unique functionality ever.

## Mission OS

### Working identity

- Internal id: `mission-os`
- Human phrase: “mission OS”
- Not a skill directory; not a resident description budget consumer

### Jobs

1. **Frontier** — maintain ordered bounded next-step labels for the active
   mission revision.
2. **Re-plan** — when reconciliation or results invalidate the frontier, rewrite
   only the affected slice; never invent new operator ends.
3. **Defer** — if a thread is valuable but not required for desired state, emit
   `deferred-interest@1` and keep the frontier on mission-critical work.
4. **Return** — every side engagement carries exact return point: mission id,
   revision, frontier label.

### Must not

- Maintain a skill-name inventory or stage-to-skill table.
- Authorize dispatch or grant permissions.
- Perform world effects (that is adapters under steward authority).
- Certify mission completion.
- Chase deferred interests unless the operator or an explicit frontier absorb
  step brings them in.

## Deferred interest contract (`deferred-interest@1`)

Minimum fields:

| Field | Meaning |
| --- | --- |
| `schema` | `deferred-interest@1` |
| `mission_id` | Owning mission |
| `summary` | One-line description |
| `criticality` | `low` \| `medium` \| `high` |
| `why_not_now` | Why it is not on the critical path |
| `suggested_next` | Optional hint for a future step/agent |
| `created_at_revision` | Mission revision when parked |
| `status` | `open` \| `absorbed` \| `discarded` |

**Proportionality:** low → one line; medium → short rationale; high → rationale
plus subject refs. Stored on the mission continuity surface (durable), not only
in chat.

## Control flow (one coordination turn)

```text
operator intent
  → manifest (create / resume / reconcile)
  → mission OS (frontier / re-plan / defer)
  → smallest blocker to justified progress
       ├─ unanswerable member-skill condition?
       │     → discover + invoke installed skill
       │     → return to exact frontier label
       ├─ authorized world effect needed?
       │     → adapter dispatch + external durable receipt
       │     → observe + checkpoint
       └─ off-mission but valuable?
             → deferred-interest@1; stay on critical frontier
  → checkpoint
  → repeat until verifying → independent acceptor
```

Iron turn rules:

- At most one consequential dispatch **or** one capability interrupt per turn.
- Checkpoint + live reconcile outrank chat/memory.
- Missing skill/adapter → degraded / `BLOCKED`, not improvisation.
- Operator re-ask only for escalation, protected state, or irreversible/material
  danger.

## Relationship to existing seats

| Seat | Relationship |
| --- | --- |
| `manifest` | Sole public entry; remains mission steward |
| `coordinate_once` / kernel | Evolve to consult mission OS for frontier/defer/return; do not fork a second driver |
| `FilesystemArtifactAdapter` | Example world-power adapter; not v1 by itself |
| `metacognate` | Owns discipline routing for unanswerable conditions |
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
| Tempting off-path thread | Deferred interest or explicit mission-critical justification |

## Testing strategy

Deterministic tests (RED → GREEN → REFACTOR) must cover:

1. Frontier re-plan after live-state contradiction.
2. Deferred interest created while critical frontier unchanged.
3. Capability interrupt restores exact return point.
4. Receipted adapter effect survives crash/reload from checkpoint.
5. Steward self-acceptance refused.
6. No copied skill-name inventory in mission OS or `manifest`.

## First implementation slice (after plan)

Build a realistic mission proof path (fixture and/or documented run):

create → approve → mission OS frontier → optional deferred distraction →
receipted filesystem write → discard in-memory state → resume from checkpoint →
reconcile → verifying → independent accept — with original operator instruction
unchanged.

This advances v1 teeth; it is **not** a release tag.

## Success criteria for this design

The design is accepted when:

1. Operator agrees mission OS is internal-in-repo, not a second public skill.
2. Discipline routing remains outside PA inventories.
3. Deferred interests and return points are specified enough to implement without
   inventing ends.
4. “helix it” special behavior is explicitly forbidden.
5. First build slice is small enough for one implementation plan.

## Open follow-ups (explicitly later)

- Whether deferred interests ever need an independent public trigger (default: no).
- Multi-adapter world paths beyond filesystem text artifacts.
- Comparative evaluation vs ordinary skilled agents.
- Repo extraction of mission OS after multiple consumers exist.
