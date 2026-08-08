# Practical Agency 1.0.0 — release criteria

Status: **criteria only — not a release candidate**. This file defines what must
be true before tagging `v1.0.0`. It is not evidence that those gates have been
met. When a candidate exists, record gate status in `RELEASE-1.0.0.md` against
the exact commit.

Claim surface: **first operator-useful major**. Authorized intent can be
installed in a declared harness, advanced through at least one bounded adapter
that emits an external durable receipt, resumed after interruption from
checkpoints, and closed only by an independent acceptor.

See [VERSIONING.md](VERSIONING.md) for the `0.1.0` vs `1.0.0` ladder.

## Prerequisites

| Gate | Requirement | Status at criteria authoring |
| --- | --- | --- |
| Prior support point | `0.1.0` tagged as an immutable support point, **or** an explicit operator exception records the missing tag as `WAIVED`/`UNMET` (never as `GO`) | unmet until `0.1.0` publishes |
| Version alignment | All live version surfaces agree on `1.0.0` for the candidate; no retag of `0.1.0` | unmet |
| Public contract | Sole public skill is `manifest`; no public skills for resume/checkpoint/reconcile/dispatch/commission/close | design invariant |

## Must-gates before tag

### 1. Live harness verification

For **every** harness listed as supported in the candidate README or release
notes (start with Cursor; add others only when declared):

| Check | Evidence |
| --- | --- |
| Source revision | Exact candidate SHA or tag |
| Installed path | Path used by the harness |
| Loaded skill count | Exactly `1` |
| Loaded skill name | `manifest` |
| Description | Present and byte-exact to the packaged skill |
| Invocation | `"manifest this"` accepted |
| Compatibility intent | `"helix it"` accepted with the same mission semantics |
| Reload / cache | Behavior recorded |
| Verification tier | Live exercise or explicit degraded tier with limits |

A structural archive test or in-process unit suite is **not** a live harness
test.

### 2. Bounded production-capable adapter path

At least one adapter that:

- performs a consequential authorized effect outside pure in-process fixtures;
- does **not** run arbitrary shell commands by default;
- returns an **external durable receipt** (hashable artifact, store object, or
  equivalent) that the checkpoint can reference;
- fails closed into visible `BLOCKED` when the substrate is unavailable.

In-memory or unittest-only adapters do **not** satisfy this gate.

### 3. End-to-end operator mission proof

One recorded proof (not only `tests/test_end_to_end_mission.py`) that:

1. creates a draft mission from verbatim operator intent;
2. approves it under recorded authority;
3. discovers capabilities dynamically (no copied inventory);
4. dispatches one authorized action through the qualifying adapter;
5. records the observed external receipt;
6. checkpoints revision N;
7. discards session memory / restarts or opens a new session;
8. loads revision N and re-anchors to live artifacts;
9. injects or observes a live-state contradiction and reopens as required;
10. dispatches a corrective authorized action when needed;
11. enters `verifying` without self-completion;
12. rejects steward self-acceptance;
13. accepts through the declared independent acceptor (`PASS`);
14. loads the final `completed` checkpoint with the original operator
    instruction unchanged.

### 4. Commission-watch honesty

Exactly one of:

- a production-faithful observer path with upstream `watch-commission@1`
  verifier receipts, and no `PROVEN` promotion from adapter success alone; or
- explicit `BLOCKED` / `UNVERIFIED_EXTERNAL_CONTRACT` when substrate or verifier
  is absent, with no invented second authority.

### 5. Conforming release process

Adapt epistemic-skills release gate classes to this repository:

| Gate class | Required outcome |
| --- | --- |
| Integrity (version/link alignment, deterministic suite, public-content, provenance) | `MET` on exact candidate |
| Harness evidence | Live or explicit tier per supported harness |
| Independent publication judgment | Gauntlet `GO` with no unresolved high-severity findings — or recorded owner exception (`WAIVED`/`UNMET`) |
| Publication identity | Annotated tag `v1.0.0` equals candidate SHA; GitHub Release body matches committed `RELEASE-1.0.0.md` |

## Explicitly `NOT CLAIMED` at 1.0.0

These remain false even after a conforming `1.0.0` tag unless separately proven
under a later version:

- daemon / hosted service / autonomous background actor
- independent ends for the agent
- universal or comparative efficacy vs ordinary skilled agents
- automatic `watch` → `manifest` routing without installation and admitted intake
- unrestricted shell as default execution
- multi-provider monitoring matrix

Comparative efficacy is a later evidence program, not a `1.0.0` honesty
requirement.

## Release-note evidence table (for future `RELEASE-1.0.0.md`)

When a candidate exists, fill:

| Gate | Status | Exact subject | Evidence | Limits |
| --- | --- | --- | --- | --- |
| `0.1.0` prerequisite | `MET` / `WAIVED` | tag or exception record | … | … |
| version/link alignment | `MET` / `UNMET` | commit SHA | … | … |
| deterministic + public content | `MET` / `UNMET` | commit SHA | … | … |
| harness evidence | tier per harness | tag/commit | … | … |
| bounded adapter + external receipt | `MET` / `UNMET` | adapter id + receipt ref | … | … |
| operator E2E mission proof | `MET` / `UNMET` | mission id + checkpoint | … | … |
| commission-watch honesty | `MET` / `UNMET` | commission or BLOCKED record | … | … |
| independent publication judgment | `GO` / `CONDITIONAL` / `NO-GO` / `WAIVED` | frozen commit | … | … |
| publication identity | `MET` / `UNMET` | tag + release | … | … |

## Anti-patterns

- Treating confirmer PASS on a `0.1` kernel candidate as `1.0.0` readiness
- Retagging or renaming `0.1.0` to manufacture a major
- Counting fixture adapters as production-capable
- Implying comparative efficacy from the major bump alone
- Self-certifying material completion of the release mission
