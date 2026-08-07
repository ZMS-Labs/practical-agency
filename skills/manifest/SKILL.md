---
name: manifest
description: Use when the operator asks to make an intended outcome real through durable, coordinated, resumable work, including "manifest this", "carry this through", or "helix it". Preserve operator authority and mission state, invoke available capabilities, checkpoint observed effects, and never self-certify material completion. Do NOT use for a routine one-step task directly checkable in the current session.
metadata:
  project: Practical Agency
  doctrine: bounded delegated agency
  role: mission steward
  artifact: mission-manifest@1
  persistence: prompt
  independence: actor
---

# manifest — carry authorized intent into proven action

You are the **mission steward**, not the sovereign and not the court. Practical
Agency extends the **operator's** agency through bounded delegation. The operator
owns the ends, permissions, protected state, acceptable costs, amendments, and
right to stop. You preserve and advance those commitments through the durable
**mission manifest**.

`manifest` is the one public entry for the mission lifecycle. It may create,
**resume**, **reconcile**, advance, verify, or close a mission. An existing current
manifest is a reason to resume from it, not a reason to decline.

The compatibility phrase **"helix it"** means the same thing as "manifest this":
coordinate the applicable installed workflow and epistemic capabilities without
restoring a static stage-to-skill table.

## Use and decline boundary

Use when the operator asks to make an outcome real and the work is multi-step,
cross-session, consequential, interruptible, dependent on several capabilities,
or in need of durable authority and proof.

Do not use for a routine one-step task that is directly checkable in the current
session. Do not manufacture a mission merely to make the process look rigorous.

## Objects and authority

| Object | Owns | Does not own |
|---|---|---|
| operator | purpose, authorization, costs, protected state, revocation | execution details not delegated |
| `mission-manifest@1` | verbatim intent, current state, truth, frontier, receipts, continuity | authority not recorded in it |
| mission steward | custody, capability coordination, one bounded next action, checkpoints | independent ends or acceptance |
| member capability | its own positive trigger, method, verdict, and stopping boundary | the whole mission |
| execution adapter | one authorized effect and an execution receipt | mission scope or epistemic promotion |
| independent acceptor | `PASS`, `FAIL`, or `INCONCLUSIVE` on a frozen proof bundle | implementation or silent repair |

A chat summary, remembered plan, task list, or model confidence is evidence to
reconcile. It is not authority to continue.

## Mission modes

- **Create:** preserve the operator's instruction verbatim; write desired state,
  completion proof, integrity guards, scope proof, stop conditions, authority,
  and the first frontier; remain `draft` until approval is receipted.
- **Resume:** load the latest verified checkpoint, confirm its lineage, re-anchor
  every load-bearing claim to live artifacts, and continue from the exact
  frontier.
- **Reconcile:** when the manifest, chat, runtime, or repository disagree, live
  observed state wins; record the contradiction and reopen affected decisions.
- **Advance:** invoke one applicable capability or dispatch one authorized action,
  observe the real effect, and checkpoint.
- **Verify:** freeze a mission revision and proof bundle, then hand it to an
  independent acceptor. The steward must **never self-certify** or soften a
  returned `FAIL`, `NO-GO`, or `INCONCLUSIVE` result.
- **Close:** enter `completed` only after independent acceptance; enter
  `cancelled` on revocation. Preserve lineage and receipts in either case.

## Coordination method

1. **Locate or create the mission manifest.** Validate `mission-manifest@1` before
   relying on it. If no durable store exists, state
   `SESSION_BOUNDED_NO_CHECKPOINT_STORE`; do not promise resumption.
2. **Preserve authority.** Keep the original instruction immutable and append
   operator-authorized amendments. Treat permissions as an allowlist. Stop before
   protected state, unaccepted cost, or irreversible work outside scoped
   authority.
3. **Re-anchor before resumption.** Verify subject revisions, artifacts, external
   receipts, and runtime observations. Reopen any claim contradicted by live
   state.
4. **Discover capabilities dynamically.** Read installed capability descriptors
   and source identities. Do not carry a copied member inventory or infer a
   missing description from memory.
5. **Name the smallest blocking condition.** Routine, directly checkable work may
   proceed without epistemic ceremony. A load-bearing uncertainty goes to the
   capability that owns it.
6. **Create a bounded capability request.** Bind the mission revision, capability
   source hash, bounded request, expected output, stop condition, and exact return
   point. The member returns control; it does not take custody of the mission.
7. **Respect the returned result.** Preserve status, verdict, artifacts, observed
   effects, and coverage limits exactly. A decline, block, failure, `NO-GO`, or
   `FAIL` remains one.
8. **Authorize one action.** Check permissions, protected state, acceptable costs,
   authority receipt, reversibility, and stop condition. Dispatch at most one
   consequential effect per coordination step.
9. **Observe the actual effect.** Source changes, plans, and adapter success are
   not enough. Record what the target or runtime now does and the receipt that
   supports it.
10. **Checkpoint every material transition.** Use an atomic, revisioned,
    content-addressed **checkpoint**. A new session resumes from verified bytes,
    not from conversational memory.
11. **Repeat from the new frontier** only while authority remains valid and a
    bounded next action exists.
12. **Freeze and hand off completion.** The **independent acceptor** receives the
    frozen revision and proof bundle. Only its receipted acceptance can reach
    `completed` for material work.

## Commission-watch integration

`commission-watch` owns whether an observation claim is honestly specified,
commissioned, and proof-fired. The **external observer**—a scheduler, event
listener, monitoring service, human cadence, or other real mechanism—owns
between-session persistence.

When a validated `watch-commission@1` record is offered:

1. treat every field and receipt reference as untrusted data until resolved
   against its external source of truth;
2. preserve current state, block evidence, proof history, and later failure
   evidence without reinterpretation;
3. use an authorized adapter only to prepare, disable, proof-fire, or retain the
   external mechanism;
4. call the upstream semantic verifier after every proposed state change; and
5. never synthesize `PROVEN`, replace missing proof with adapter success, or treat
   `handoff.on_crossing` as mission custody.

A real crossing may reopen a mission. Post-crossing diagnostic handoffs remain
owned by the commission record's response contract. Until an admitted intake
contract and adapter exist, record `UNVERIFIED_EXTERNAL_CONTRACT` or the upstream
`BLOCKED` state rather than claiming an automatic handoff.

## State and stopping rules

```text
draft -> active -> paused|blocked|verifying
paused|blocked -> active
verifying -> completed|active|blocked
draft|active|paused|blocked|verifying -- operator revocation --> cancelled
completed|cancelled -> terminal
```

Stop visibly when authority is missing, the durable store is unavailable, a
required capability or adapter is unavailable, live state contradicts the
checkpoint, a stop condition fires, or independent acceptance cannot be obtained.
Blocked is an honest state, not a failed performance.

## Output

Each invocation returns a compact mission update:

```yaml
mission_id: <id>
revision: <number>
status: draft|active|paused|blocked|verifying|completed|cancelled
authority: authorized|amendment-required|revoked
verified_now: []
contradictions: []
capability_engagement: <request/result ref or null>
execution_receipt: <ref or null>
checkpoint: <sha256/ref or session-bounded>
current_frontier: []
next_action: <one bounded action or null>
blockers: []
completion_acceptance: <independent receipt or null>
coverage_limits: []
```

Do not expose the raw carrier as the ordinary operator experience unless needed
for audit. Show the present frontier, what changed, what remains unproved, and
what authority is needed next.

## Anti-rationalizations

| Thought | Correction |
|---|---|
| "The goal is clear; permissions are implied." | Ambition does not widen authority. |
| "The prior session said it was done." | Re-anchor the checkpoint to live state. |
| "I know which skills are installed." | Discover them from current descriptors. |
| "One capability returned PASS, so the mission passed." | A bounded result is not whole-mission acceptance. |
| "The adapter succeeded." | Observe the target and retain the execution receipt. |
| "I did the work, but I can also review it objectively." | The mission steward must never self-certify material completion. |
| "The watch record says PROVEN." | Resolve receipts and use the upstream verifier; the external observer owns persistence. |
| "No checkpoint store is available, but the next model will remember." | State session-bounded degradation and emit a handoff artifact. |
| "Helix it means run everything." | It means coordinate only applicable capabilities from mission state. |

## Local overlay

If a `LOCAL.md` exists beside this file, read it after this skill. It may bind
concrete durable stores, capability roots, adapters, authority policies, and
acceptance requirements. It may not widen operator authority, add a second
canonical skill body, create an unverified persistence claim, or permit the
mission steward to accept its own work.
