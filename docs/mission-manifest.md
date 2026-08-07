# `mission-manifest@1` field guide

The mission manifest is the durable contract of record for one authorized mission.
It is not a prompt transcript, task list, or claim that a background agent exists.

## Top-level sections

| Section | Purpose |
| --- | --- |
| `authority` | Operator identity, verbatim instruction, append-only amendments, permissions, protected state, acceptable costs, escalation rules, and revocation. |
| `outcome` | Desired state, completion proof, integrity guards, scope proof, and stop conditions. |
| `truth` | Subject references, verified facts, assumptions, contradictions, and unknowns. |
| `state` | Closed lifecycle status, completed actions, current frontier, blockers, and one next action. |
| `capabilities` | Current discovery results, bounded invocations, unavailable members, and visible degradation. |
| `continuity` | Checkpoint lineage, durable artifacts, decisions, external handoffs, and commission records. |
| `integrity` | Material-work actors, required gates, unresolved verdicts, and independent completion receipt. |

The semantic validator rejects unknown top-level and section fields so accidental
schema drift cannot be interpreted optimistically.

## Lifecycle

```text
draft -> active -> paused|blocked|verifying
paused|blocked -> active
verifying -> completed|active|blocked
draft|active|paused|blocked|verifying -- operator revocation --> cancelled
completed|cancelled -> terminal
```

`completed` requires a receipted acceptor that is not listed among the material
work actors. A live contradiction creates a new active revision; it does not
rewrite the old checkpoint.

## Authority

`authority.instruction` is immutable across normal revisions. Authorized changes
are appended to `authority.amendments` with the new revision, operator identity,
authorization reference, and time. Revocation requires the recorded operator, a
durable authority reference, and a timestamp; it is the only route to
`cancelled`.

Permissions and acceptable costs are allowlists. Protected state is deny-before-
action. Irreversible or explicitly escalated work requires fresh operator
approval rather than inferred ambition.

## Checkpoints

A checkpoint contains the entire manifest plus events and receipts. Its canonical
JSON bytes are SHA-256 addressed. The `LATEST` pointer is atomically replaced only
after checkpoint bytes are durable. Loading verifies the pointer, checksum,
identity, revision, and manifest semantics.

Conversation summaries may help locate a mission, but they cannot replace a
verified checkpoint.

## Capability engagement

Capabilities are discovered from current descriptors. Requests bind the mission
revision, capability source hash, bounded question or action, expected output,
stop condition, and exact return point. A result may complete, decline, block, or
fail the bounded engagement; it cannot implicitly complete the entire mission.

## External watches

`continuity.watch_commissions` may retain an externally verified
`watch-commission@1` record or a visible external-contract status. Practical
Agency never promotes the upstream state itself. A real crossing may reopen the
mission while the commission record's post-crossing diagnostic handoff remains
separate.

See `examples/minimal-mission.json` and
`examples/watch-commission-mission.json` for complete carriers.
