# Mission manifest — `mission-manifest@1`

The mission manifest is Practical Agency's canonical durable artifact. JSON is
the authoritative representation in v0.1; Markdown summaries are projections and
cannot replace a validated checkpoint.

## Required sections

| Section | Purpose |
| --- | --- |
| `authority` | Operator identity, verbatim instruction, append-only amendments, permissions, protected state, cost, escalation, revocation |
| `outcome` | Desired state, completion proof, integrity guards, scope proof, stop conditions |
| `truth` | Revision-bound subjects, verified facts, assumptions, contradictions, unknowns |
| `state` | Closed mission status, completed actions, frontier, blockers, next action |
| `capabilities` | Discovery time and available, invoked, unavailable, degraded capabilities |
| `continuity` | Prior checkpoint, artifacts, decisions, external handoffs, watch commissions |
| `integrity` | Self-acceptance prohibition, gates, unresolved verdicts, independent acceptor |

The complete structural carrier is
[`contracts/mission-manifest.schema.json`](../contracts/mission-manifest.schema.json).
Cross-field semantic rules are enforced by
`practical_agency.validation.validate_manifest_dict`.

## Lifecycle

```text
draft -> active -> paused -> active
active|paused|verifying -> blocked -> active
active -> verifying -> completed
verifying -> active|blocked on FAIL or INCONCLUSIVE
nonterminal -> cancelled on revocation/cancellation
```

No caller can assign status directly through the transition API.

## Checkpoints

A checkpoint stores canonical JSON bytes and a separate SHA-256 receipt. Revision
files are immutable: the same mission/revision cannot be overwritten with
different bytes. A prose summary, stale chat, or partial temporary file is not a
checkpoint.

On resumption, load the highest valid receipt, verify its bytes, then compare
stored verified facts with live observations. Contradictions and missing live
observations reopen dependent work.

## Example

Start from [`examples/minimal-mission.json`](../examples/minimal-mission.json).
Preserve `authority.instruction` byte-for-byte. Use `authority.amendments` for
later operator changes rather than editing the original instruction.
