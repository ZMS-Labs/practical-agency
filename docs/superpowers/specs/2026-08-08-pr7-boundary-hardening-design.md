# PR #7 boundary-hardening design

**Date:** 2026-08-08  
**Status:** Approved for implementation by the repository operator  
**Scope:** Hardening of the cumulative mission-kernel and mission-OS integration in PR #7. No live deployment and no merge.

## Problem statement

PR #7 has a coherent intended architecture, but several guarantees are currently enforced only on cooperative paths. The implementation must make those guarantees true at the boundaries where stale, malformed, replayed, forged, or partially failed inputs matter.

The governing invariants are:

1. Capability discovery is dynamic and forward-compatible. Practical Agency does not copy an external skill inventory.
2. The steward is the sole writer of mission frontier state. Watch crossings and capability selection cannot mutate that state directly.
3. No dispatch or capability interruption may consume a frontier until a matching mission-OS proposal has been applied.
4. Authorization is rechecked at the world-effect boundary. A caller-created decision is not an authorization token.
5. Events, proposals, decisions, and receipts are bound to mission identity, revision, and canonical payload.
6. Return points identify a real frontier entry; invalid indexes fail closed.
7. New frontier aims require resolvable basis records. Deferral of potentially critical work fails closed when clearance is ambiguous.
8. World effects are journaled before execution and finalized atomically afterward. Crash windows remain visible rather than being represented as success.
9. Tests exercise the claimed runtime behavior, including negative and interrupted paths.

## Design

### Dynamic discovery

Descriptor top-level keys remain strict because they define the provider contract. Metadata is an extension namespace: recognized authority-sensitive fields are validated strictly, while unknown metadata fields are preserved as opaque values. A CI interoperability test discovers the pinned upstream skill package from the directory already fetched by CI and verifies every descriptor without enumerating member names.

### Revision-bound event envelope

`MissionEvent` implements `mission-event@1`: `event_id`, `mission_id`, `expected_revision`, `kind`, `actor_ref`, `data`, and `observed_at`. Application rejects mission mismatch, stale revision, and replay before mutation. Successfully applied event IDs are persisted in continuity.

Call sites use a helper that derives mission ID and expected revision from the live manifest and generates a unique event ID. Tests may construct explicit envelopes to exercise stale and replay behavior.

### Bound mission-OS proposals

A proposal carries `proposal_id`, `mission_id`, `base_revision`, `kind`, `payload`, and `payload_sha256`. The hash is computed over canonical JSON containing the proposal identity and payload. Apply verifies all bindings before evaluating the proposal.

A frontier proposal includes:

- `frontier`: the proposed replacement slice;
- `replace_range`: a bounded `[start, end)` range;
- `basis_refs`: references resolving to existing instruction, amendment, desired-state, live-contradiction, or recorded-observation evidence;
- `contradiction_refs`: existing contradiction records only;
- `deferred_interests`: deferrals with explicit critical-path clearance.

The first slice may still replace the full frontier, but it does so explicitly using `[0, len(current_frontier))`.

### Applied-frontier record

Applying a frontier proposal records a decision containing proposal identity, base revision, resulting revision, canonical frontier hash, and return-point contract. Coordinator gates verify that record against the live frontier. Both execution and capability interruption require it; the requirement is not caller-configurable.

### Dispatch authority

A coordination decision records the canonical request hash and the apply record it consumed. `dispatch_once` treats the decision as untrusted input and repeats:

- request shape validation;
- mission/revision binding;
- applied-frontier verification;
- authorization against the live manifest;
- request-hash verification; and
- adapter identity binding.

Adapters expose a stable `adapter_ref`. An adapter can dispatch only requests whose capability ID it declares.

### Watch crossings

The commission watcher emits a crossing observation and external handoff containing the unanswered condition, expected output contract, and return point. It does not alter the frontier, mission status, next action, or select named epistemic skills. A later mission-OS proposal may cite the recorded crossing as a basis and the steward may apply it.

### Return points

All return-point creation and consumption uses one validator. A numeric frontier index must resolve to an existing frontier item. Empty-frontier cases use no numeric index and must be represented explicitly; the current first slice rejects interruption when no real return point exists.

### Critical-path deferral and no-invented-ends

Machine-verifiable provenance is used instead of semantic overclaiming. Every frontier label must cite resolvable basis records. Every deferred interest must include either an explicit recorded clearance or be refused as `DEFER_CRITICAL_PATH_AMBIGUOUS`. Exact-string comparison may be used as an additional conservative signal but never as the sole clearance oracle.

Documentation will state that the kernel verifies provenance and recorded clearance; it does not claim to prove natural-language entailment.

### Crash-safe execution receipts

The filesystem adapter derives journal filenames from a SHA-256 digest of the request ID. It atomically writes a `prepared` journal before the effect, performs the atomic artifact replacement, and atomically finalizes the journal as `committed`. If finalization fails after the effect, it best-effort writes an atomic `uncertain` journal and raises; it never returns an unreceipted success.

Failure-injection hooks are constructor-only test controls. They do not create a shell or production bypass.

The steward records execution-receipt identity, external receipt ref, artifact digest, adapter ref, and coverage limits in continuity. Resume tests reload only checkpointed state and independently verify the external receipt and artifact digest.

## Compatibility and migration

This is a pre-release repository. The hard gates take precedence over preserving permissive call signatures. Small compatibility helpers may remain where they cannot weaken enforcement. Existing fixtures are migrated to the revision-bound event helper.

Continuity gains additive fields for processed event IDs and execution receipts. Manifest validation and schema are updated together.

## Verification oracle

A green result is sufficient only when it exercises the asserted runtime boundary. Required evidence:

- pinned-upstream discovery test with unknown metadata;
- stale, cross-mission, and replay event refusals;
- proposal hash/mission/revision tamper refusals;
- capability interruption before apply refusal;
- forged and mutated dispatch refusal;
- wrong-adapter refusal;
- watcher cannot mutate frontier before apply;
- invalid return-point refusal;
- fabricated basis and ambiguous deferral refusals;
- crash injection before effect and after effect/finalization;
- checkpoint-only receipt resume verification;
- full unit, contract, package, harness, public-content, wheel-build/install, CodeQL, and DCO checks.

## Non-goals

- No live capability execution outside temporary test directories.
- No Home Assistant or other operator environment changes.
- No merge of PR #7.
- No static inventory of epistemic skills.
- No claim that deterministic code proves unrestricted natural-language entailment.
