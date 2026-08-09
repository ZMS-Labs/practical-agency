# External observation capability boundary

**Date:** 2026-08-09
**Status:** Approved ownership decision; interface design only
**Owning issue:** [ZMS-Labs/practical-agency#9](https://github.com/ZMS-Labs/practical-agency/issues/9)

## Decision

Practical Agency does not own workstation collection, transport, deployment,
or evaluator infrastructure. It owns only the mission-control boundary by
which an authorized mission may request evidence from an external observation
provider and consume a typed, receipt-bound result.

The device-specific provider and its operational deployment belong in the
private infrastructure repository that owns the observed estate. This keeps
Practical Agency a deterministic mission-control kernel rather than a fleet
agent, scheduler, telemetry service, or device manager.

## Considered approaches

### Practical Agency owns the complete observation mechanism

Rejected. Collector installation, process lifetime, transport, retries,
buffering, and cluster delivery are replaceable substrate concerns. Owning them
here would conflict with the no-daemon/no-scheduler boundary and couple the
public kernel to one private estate.

### The estate system owns everything

Rejected. The estate system may define and produce observations, but it must
not bypass mission authority, broker coordination, durable checkpointing, or
typed proof when an agentic mission requests those observations.

### Split provider boundary

Selected. Practical Agency governs the request and proof lifecycle. An external
provider owns observation mechanics. The estate evaluator owns the meanings of
its evidence fields and the resulting coverage classification.

The split is falsified if changing collector or transport technology requires
changing Practical Agency mission semantics. A compliant provider should be
substitutable without changing authority, checkpoint, receipt, or verifier
rules.

## Practical Agency responsibilities

An eventual bounded observation capability may:

1. derive an evidence-only request from durable mission authority;
2. bind the request to mission id, mission revision, request id, provider id,
   requested coverage, maximum evidence age, and permitted disclosure fields;
3. issue one broker grant for that request;
4. receive a typed provider result and an external durable receipt;
5. verify request/result/receipt binding, producer identity, capture time,
   freshness, schema version, duplicate or replay status, and declared coverage;
6. checkpoint verified, contradicted, partial, unavailable, or stale results;
7. propagate `unknown` instead of manufacturing successful current evidence;
   and
8. preserve a hard evidence-only boundary: the capability cannot authorize or
   perform commit, push, stash, checkout, prune, delete, cleanup, or any other
   mutation.

The first implementation, if separately approved, is on-demand from an active
`manifest` engagement. This design creates no second public skill, background
worker, scheduler, resident service, generic shell adapter, or inbound control
channel.

## External provider responsibilities

The external provider owns:

- source-specific enumeration and observation;
- local installation and removal, if a local component is necessary;
- process lifetime and resource policy;
- outbound transport and authentication;
- replay protection, retries, buffering, and outage behavior;
- minimized source and repository identity mapping;
- integration with the external read-only evaluator; and
- operator-visible manual fallback.

Those implementations are not bundled into the Practical Agency plugin. The
provider may be replaced without changing the public mission contract.

## Result semantics

Practical Agency does not reinterpret a provider's domain fields. It requires
the result to distinguish at least:

- verified current observation;
- partial observation;
- missing or inaccessible configured coverage;
- stale observation with last capture time;
- malformed or contradictory evidence;
- provider failure or timeout; and
- evaluator or transport unavailability.

Silence is never a clean result. Missing, stale, malformed, contradictory, or
failed evidence remains `unknown` at the consuming mission's claim boundary.

## Data and authority limits

Requests and results use stable source/repository/clone identifiers where
possible. They do not require file bodies, diffs, credentials, arbitrary
environment variables, raw command output, or centrally stored absolute local
paths. Provider evidence is lower-provenance data and cannot configure its own
trust tier or grant downstream authority.

## Delivery boundary

This document resolves ownership but does not ship an observation adapter. An
adapter becomes justified only by an approved mission with a real provider,
versioned result contract, external receipt, semantic verifier, and live
interruption/failure proof. Until then, issue #9 remains an interface-design
record rather than a production claim.
