# Practical Agency 0.1.0 release boundary

This document describes the candidate boundary. It is not a claim that a tag,
package registry release, live harness installation, or background service exists.

Tagging `0.1.0` does **not** satisfy
[RELEASE-1.0.0-CRITERIA.md](RELEASE-1.0.0-CRITERIA.md). See
[VERSIONING.md](VERSIONING.md) for the claim-surface ladder.

Climb tip under review: branch `cursor/climb-0-1-a955` (hardened PR #4 kernel plus
versioning docs).  
Prior `main@57f37ce` freeze: CONDITIONAL —
[`../gauntlet-runs/practical-agency-0.1.0-candidate-2026-08-07/`](../gauntlet-runs/practical-agency-0.1.0-candidate-2026-08-07/).  
Climb reconcile:
[`../gauntlet-runs/practical-agency-0.1.0-climb-2026-08-08/RECONCILE.md`](../gauntlet-runs/practical-agency-0.1.0-climb-2026-08-08/RECONCILE.md).  
Verification:
[`VERIFICATION-0.1.0-climb-tip.md`](VERIFICATION-0.1.0-climb-tip.md).

## Proven by deterministic fixtures

- strict mission-manifest validation and canonical round trips;
- verbatim operator-intent preservation and append-only amendments;
- closed authority and state transitions;
- completion proof and declared gates required before verification;
- evidence-bearing independent acceptance or rejection for material completion;
- atomic hash-bound checkpoints, canonical path confinement, and crash/restart
  recovery;
- live-state contradictions invalidate affected proof, create load-bearing
  reconciliation markers, open one bounded repair frontier, and require fresh
  observation before renewed verification;
- dynamic capability discovery without a copied inventory;
- exact capability request/result and execution request/receipt binding;
- one bounded dispatch per decision and exact return-point restoration;
- blockers and unresolved verdicts permit only the exact recorded remediation
  execution, refuse fail-closed when no remediation action is recorded, and
  refuse forged direct dispatch while remediation bears load;
- refusal to rewrite `NO-GO` or `FAIL`;
- commission adapter operations occur only after the injected upstream verifier
  accepts the input contract;
- revoked or non-operating commissions cannot reopen missions; and
- disablement on revocation updates retained current state while preserving
  historical proof.

## Pinned cross-repository compatibility

Permanent CI checks out `ZMS-Labs/epistemic-skills` at immutable revision
`6e26484a9cae7629b233734fe5121137ba9168a8` and uses the actual
`watch-commission@1` semantic verifier and committed example corpus.

The integration fixtures prove that:

- upstream accepted and rejected examples preserve their oracles through the
  Practical Agency intake boundary;
- Practical Agency's disabled preparation is accepted upstream as
  `BLOCKED: KILL_SWITCH_UNPROVEN`; and
- `manifest` is rejected as a post-crossing `handoff.on_crossing` value.

This is compatibility evidence at one pinned revision. It is not evidence that
receipt references are authentic, that a production adapter exists, or that an
automatic `watch` → `manifest` route has been admitted.

## Structurally verified

- exactly one public skill named `manifest`;
- resident description within the recorded 420-byte v0.1 ceiling;
- harness metadata uses the canonical root `skills/` body without a copied skill
  inventory;
- all committed JSON files parse; and
- schemas, package boundaries, public-content checks, and Python compilation pass.

## Harness evidence so far

- Cursor cloud workspace: `structural-archive-only` —
  [`harness-observations/cursor-cloud-2026-08-08.md`](harness-observations/cursor-cloud-2026-08-08.md).
  Does **not** close P2-HARNESS-LOAD.
- Checklist template:
  [`HARNESS-LOAD-CHECKLIST-0.1.0.md`](HARNESS-LOAD-CHECKLIST-0.1.0.md).

## Unverified until separately exercised

- live loading, discovery, invocation, and cache behavior in each supported
  harness;
- production execution, checkpoint, scheduler, monitor, or notification adapters;
- external watch receipt resolution against a real provider;
- operational revocation of a production mechanism; and
- comparative end-to-end benefit over an ordinary skilled agent.

## Not claimed

- autonomous background operation;
- independent machine ends or sovereign authority;
- universal efficacy or safety;
- a production observer commissioned by installing this package;
- an automatic cross-package commission handoff; or
- permission for the mission steward to certify its own material work.
