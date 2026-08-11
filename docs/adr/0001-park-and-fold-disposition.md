# ADR 0001 — Park practical-agency; fold its custody semantics into epistemic-skills

**Status:** accepted (operator-directed, 2026-08-11)
**Date:** 2026-08-11
**Canonical estate record:** ADR-184 in the operator's private governance registry — this file is its public-safe projection (numbered locally; this repo has no ADR sequence of its own)

## Context — genesis and lineage

practical-agency was created 2026-08-07 as the successor to "helix," a rejected
guided-path/router seat in the operator's skill estate: the underlying need was
consistent, durable application of discipline to consequential work. The repo's
founding telos ("optimizes delegation, not execution"; bounded delegated agency;
sole public skill `manifest`) was recorded in-repo from day 0, but the creation
decision itself was not contemporaneously recorded in estate governance — this
ADR closes that gap.

Day 0 ran a multi-harness bake-off producing three parallel kernel
implementations; one was adopted (PR #3) and two were discarded (~40% of all
commits). No contemporaneous selection rationale was recorded. That rationale is
now unrecoverable; this ADR records the gap honestly rather than reconstructing
one.

Over four days (2026-08-07 → 08-10), roughly 200 commits across three agent
harnesses produced: a deterministic stdlib mission kernel, a Codex-plugin live
engagement alpha (MCP controller + deny-hooks, receipt-backed), an unusually
rigorous claims-hygiene apparatus (adverse review verdicts preserved unrewritten;
checkpoint/receipt hashes that verify bit-for-bit), and an OS-level
three-process kill/resume/repair proof.

## The review

An operator-side adversarial review (full gauntlet, deep depth, 2026-08-10;
record retained in the operator's private archive, hash-chain verified) returned:

- **Verdict: NO-GO on unconditional continuation — explicitly NOT archive.**
  Every evaluator seat declined to recommend archiving. Judge's ruling: "a real,
  rare, mechanically-demonstrated capability that is currently unwired."
- The decisive finding: the repo's own adoption falsifier ("will operators
  invoke it instead of bypassing it?") had never been scheduled, while all value
  accumulated on one unmerged mega-branch whose headline proof drifted from its
  tip.
- A pre-committed demand×vehicle decision rule was published before either
  discriminator ran. **Vehicle** (fold-feasibility spike): PASS — a ~750-line
  from-scratch stdlib shim reproduced pathless discovery, drift
  detection/refusal, and worker-cannot-self-accept enforcement, with the honest
  residual that PA's *external* enforcement boundary (harness hooks) was not
  reproduced and must come from harness machinery in any design. **Demand:** the
  operator chose the custodian experience, contracts-first, with epistemic-skills
  as the contract home.

## Decision

1. **Fold executed.** The custody semantics live on as the `mission-custody@1`
   contract family in ZMS-Labs/epistemic-skills (schemas + stdlib verifier +
   examples corpus + CI, on the watch-commission@1 pattern), a small custody
   core (atomic chained checkpoints, pathless discovery, drift → recorded
   reopen, tiered acceptance with kernel-refused self-certification, and a
   **clearable FAIL path** — deliberately designing out this kernel's reject
   dead-end), and a single `manifest` skill. See epistemic-skills PR #114.
2. **This repository is PARKED as prior art and proof corpus.** No net-new
   capability lands here. The kernel, its proofs, its claims-discipline record,
   and all branches are preserved. Nothing is deleted.
3. **Open PRs and issues are closed as parked**, each with a pointer to this
   ADR. Branches remain.
4. **`main` is a known-defective day-0 surface — do not release from it.** It
   retains the coordinator authority-bypass (hardcoded fixture-path
   re-authorization after refusal) and the reject dead-end; the live branch
   (`codex/manifest-live-engagement`) fixed the bypass, checkpoint fabrication,
   truth-ledger writability, and resume validation, and retains only the reject
   dead-end. The README banner records this.
5. **Live mission runtime state is orphaned by park, not deleted.** Untracked
   `missions/` state on developer checkouts (including the still-active
   `climb-pa-0-1` mission whose governed artifact exists only on the live
   branch) is terminated by this disposition; the drift such a mission would
   have surfaced on its next engagement is hereby acknowledged instead of
   discovered.

## Revival condition

Reopen active development here only if a real custodied mission demonstrates
semantics the folded substrate cannot express (the fold spike's falsifier
reversed), or if the folded design's enforcement stage produces evidence that a
standalone kernel boundary is required after all.

## Consequences

- The seat this repo pioneered — recorded authority, durable checkpoints,
  drift re-anchoring, independent acceptance, packaged portably — continues
  under a maintained home with CI teeth.
- The four-day construction record remains fully inspectable here, including
  its honest failure notes; its strongest artifacts (the three-process proof,
  the Codex deny-hook engagement receipts) remain reproducible from this tree.
- Comparative efficacy versus an ordinary skilled agent remains, as this repo
  always stated, unestablished — that question transfers to the folded
  design's tracer-mission retro.
