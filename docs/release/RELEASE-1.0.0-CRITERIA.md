# Practical Agency 1.0.0 — release criteria

Status: **criteria only — not a release candidate**. This file defines what must
be true before tagging `v1.0.0`. It is not evidence that those gates have been
met. When a candidate exists, record gate status in `RELEASE-1.0.0.md` against
the exact commit.

Claim surface: **first operator-useful major**. Authorized intent can be
installed in a declared harness, advanced through at least one bounded adapter
that emits an external durable receipt, resumed after interruption from
checkpoints, and closed only through independently evaluated acceptance.

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
- is reachable only through the coordinator's request-bound, one-use dispatch
  grant and rejects direct invocation;
- does **not** run arbitrary shell commands or generic executables by default;
- returns an **external durable receipt** that names the observed artifact and
  can be verified independently;
- records a typed verifier result bound to the mission, request, adapter,
  artifact, observation, and receipt rather than treating a string reference as
  proof; and
- fails closed into visible `BLOCKED` when the substrate is unavailable.

In-memory or unittest-only adapters do **not** satisfy this gate. An allowlist of
Python, npm, git, or similar general executables is not a sandbox. Such execution
requires a real OS or container boundary with explicit resource, filesystem,
network, environment, executable, and argument policy.

### 3. End-to-end operator mission proof

One recorded proof, outside a single in-memory test process, that:

1. creates a draft mission from verbatim operator intent;
2. approves it under recorded authority;
3. lets a new process discover the unique active mission from a workspace root
   without receiving the mission id or directory;
4. dispatches one authorized action through the qualifying broker and adapter;
5. records the observed external receipt and a typed verifier result;
6. checkpoints revision N;
7. terminates the acting process without handing in-memory mission state to its
   successor;
8. lets another process discover and load revision N from durable storage;
9. injects or observes a live-state contradiction and persists the reopened
   state;
10. dispatches a corrective authorized action through the same broker boundary;
11. enters `verifying` without self-completion;
12. lets a third process independently re-observe the final artifact and receipt;
13. rejects steward self-acceptance;
14. accepts through a distinct principal with evidence, or explicitly records
    the weaker `declared-role-separation` assurance; and
15. loads the final `completed` checkpoint with the original operator
    instruction unchanged and the external receipt still valid.

The proof must state its exact source commit or exact tested-tree fingerprint.
An executable process test may establish the mechanism; a release claim still
needs retained evidence against the immutable candidate commit.

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
- unrestricted shell or generic executable execution as a default adapter
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
- Presenting process separation as proof of distinct OS or organizational principals
- Accepting receipt-reference strings as verified observations
- Calling an executable allowlist a sandbox
- Implying comparative efficacy from the major bump alone
- Self-certifying material completion of the release mission
