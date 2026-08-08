# Arbitration — Mission OS / Manifest v1 design

**orchestration:** manual-degraded  
**panel:** concurrent isolated Task lenses (adversarial / constructive / metatextual);
arbitrator = authoring session (same model family — not cross-family)

## Conflict ledger (material)

| Tension | Ruling | Synthesis / residual |
| --- | --- | --- |
| Durability claim vs closed schema | **UPHELD** P1 | Design must lock additive optional field rule before “durable defer” language |
| Dual frontier ownership | **UPHELD** P1 | Sole durable carrier `state.current_frontier`; OS proposes; steward/kernel sole writer |
| OS auto-applies then dispatches | **UPHELD** P1 | Typed proposal + apply/accept event before dispatch |
| Re-plan invents ends | **UPHELD** P1 | Closed patch; instruction/desired_state immutable without amendment |
| Defer parks critical path | **UPHELD** P1 | Refuse defer when required for unmet completion/scope proof; ambiguous → stay or escalate |
| High absorb without amendment | **UPHELD** P1 | Authority amendment / explicit operator absorb required for `high` |
| Soft Helix / PA routing | **UPHELD** P2 | PA emits condition + return point only; selection outside PA |
| Worth / v1 teeth overclaim | **UPHELD** P2 | Demote worth language; fixture ≠ field v1 |
| Design self-accept | **UPHELD** P2 | Operator must accept **amended** design; authoring session cannot close |
| Second SKILL.md risk | **OVERRULED** as P1 | Downgraded P3 surface-creep; sole-skill iron already clear |
| Comparative efficacy | **OVERRULED** as open defect | Correctly NOT CLAIMED |

## Computed verdict rule

- Open P1 → NO-GO  
- No open P1, open P2 → CONDITIONAL  
- P1+P2 closed → GO  

## Verdict

**NO-GO** against accepting the **unamended** design as implementation-ready.

After design amendments land that close the P1 cluster below, re-score. Expected
post-amendment ceiling in this orchestration: **CONDITIONAL** (P2 independence /
claim-honesty remain until operator accepts the amended tip).

## P1 conditions (must close in design before writing-plans)

1. **P1-FRONTIER-SOLE-WRITER** — Name `state.current_frontier` as sole durable
   frontier; mission OS emits proposals only; steward/kernel applies under one
   revision/checkpoint authority.
2. **P1-OS-PROPOSAL-ACCEPT** — Typed OS proposal + recorded apply before
   dispatch/capability interrupt may use that frontier.
3. **P1-REPLAN-NO-ENDS** — Re-plan patch closed; cannot alter
   `authority.instruction` / `outcome.desired_state` without append-only amendment;
   frontier labels are conditions/outcomes, never skill names.
4. **P1-RETURN-INDEX** — Return points include `frontier_index` + label; re-plan
   invalidates or explicitly rebinds open return points.
5. **P1-DEFER-CRITICAL-PATH** — Cannot defer work required for unmet
   completion/scope proof; ambiguous necessity → keep on frontier or escalate.
6. **P1-HIGH-ABSORB-AMEND** — Absorbing `criticality=high` requires operator
   authority event (amendment and/or explicit absorb approval).
7. **P1-DEFER-SCHEMA-RULE** — Lock additive optional `continuity.deferred_interests`
   under still-`mission-manifest@1` (default `[]`, old checkpoints migrate) **or**
   an explicit schema epoch — no unschematized durability claim.

## P2 conditions (block treating design as fully settled)

1. **P2-NO-PA-ROUTING** — Control flow: PA emits unanswerable condition + return;
   does not select/invoke named epistemic skills.
2. **P2-FIXTURE-NOT-V1** — First slice may be fixture; cannot satisfy RELEASE-1.0
   world-power / “real teeth” by itself.
3. **P2-WORTH-LANGUAGE** — Remove or demote “worth the investment” as established bar.
4. **P2-OPERATOR-ACCEPT-AMENDED** — Operator durable assent on amended revision;
   authoring session must not self-accept.
5. **P2-ORCH-LABEL** — Design header carries orchestration / epistemic-review status.

## Return point

After P1 amendments land in the design doc: operator reviews amended tip → if
accepted, invoke **writing-plans** for implementation. Do not implement from the
unamended brainstorming draft.
