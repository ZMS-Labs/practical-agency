# What would give `manifest` real teeth?

Status: **operator-facing definition** under mission `climb-pa-0-1` (approved
2026-08-08). This is not a claim that the system is proven useful in production.

`manifest` has teeth only when it changes what an agent **may do**, what may
count as **done**, and what **survives** when the chat dies — in ways a goal
note, a todo list, or an ordinary skilled agent does not.

## Not teeth (already exists / easy to fake)

| Lookalike | Why it is not enough |
| --- | --- |
| Goal / `write-goal` completion contract | Names desired state and proof; does not custody authority, dispatch, or resume against live state |
| Plan / todo / checklist | Structures work; rarely binds revocation, protected state, or independent acceptance |
| Prompt prose (“preserve the user’s intent”) | Evaporates under compaction; cannot refuse an illegal transition |
| In-process fixtures alone | Prove kernel functions; do not prove interruption survival or an external receipt |
| Receipt-shaped strings | Name alleged evidence without binding a verifier observation to the request and artifact |
| Router / skill inventory / “helix table” | Ceremony and drift; Practical Agency deliberately refuses this seat |

If removing `manifest` would not change stop rules, completion rules, or
post-interruption defensibility, it has no teeth.

## Teeth = four powers

### 1. Negative power — it can stop you

Permissions are allowlists. Protected state and costs are first-class.
Revocation cancels consequential progress. The steward may not invent ends or
rewrite the operator’s instruction. Production effects require a request-bound,
one-use broker grant; the filesystem adapter rejects direct calls.

**Falsifier:** after revocation, outside permissions, or around the broker,
consequential work still proceeds “because it was useful.”

### 2. Continuity power — it outlives the chat

`mission-manifest@1` plus atomic checkpoints are the contract of record. A new
process discovers the one active mission from the workspace root, rather than
being handed an in-memory mission path. Resume re-anchors to live artifacts and
receipts; contradictions reopen. Memory and summaries are untrusted until
checked.

**Falsifier:** a new session continues from a chat summary while a checkpoint or
live artifact disagrees, and nobody notices.

### 3. World power — intent can touch reality under authority

At least one bounded adapter performs a consequential authorized effect and
returns an **external durable receipt**. In-memory fixtures do not count.
Missing substrate becomes visible `BLOCKED`, not silent prose success.

The admitted production path is `filesystem-artifact@1`. It writes only bounded
text artifacts under configured prefixes and does not expose Python, npm, git,
an arbitrary executable, or shell evaluation. A fixed proof runner may exercise
the known mission protocol; it is not a generic command adapter.

**Falsifier:** “mission complete” with only narrative artifacts for a claim that
required an external effect, or an adapter can be invoked around the broker.

This is the gap between a custody kernel and **`1.0.0` / v1** (first
operator-useful major). A trustworthy vertical path is necessary but is not by
itself v1. See [VERSIONING.md](VERSIONING.md).

### 4. Proof power — the worker cannot bless the work

Material completion depends on a typed verifier result bound to the mission
revision, execution request, observed artifact, and external receipt. The latest
verifier result controls the proof target; a contradiction invalidates stale
proof and opens reconciliation.

The steward may not self-accept. Acceptance distinguishes two assurance levels:

- `externally-proven`, which remains unavailable until a principal-authentication
  verifier can validate the evidence rather than trusting a reference string;
- `declared-role-separation`, which is honest role separation without claiming
  OS-account or organizational independence.

Adapter success is not mission completion. Watch adapter success is not
`PROVEN`.

**Falsifier:** a receipt-reference string alone satisfies completion, the worker
marks the mission completed, or declared role separation is presented as proven
principal independence.

## Current trustworthy vertical path

The fixed multi-process proof demonstrates one narrow end-to-end path:

1. initialize one active filesystem-artifact mission;
2. let process A discover it from the workspace root, dispatch through the
   broker, persist the external receipt and typed verification, then terminate
   abruptly;
3. alter the observed artifact outside the mission process;
4. let process B discover and load only the durable checkpoint, detect the
   receipt/artifact contradiction, persist the reopened state, repair through
   the broker, and checkpoint `verifying`;
5. let process C discover the mission, independently re-observe the latest
   artifact and receipt, verify steward self-acceptance is rejected, and accept
   with `declared-role-separation`.

The process proof establishes process interruption and durable reconstruction.
It explicitly does **not** claim OS-account separation, a daemon, a generic
execution sandbox, live harness invocation, or comparative usefulness.

## What would make it worth invoking

`manifest` is worth using when the operator needs **bounded continuation of
will**, not another place to write a goal:

1. The work is multi-step, cross-session, or consequential enough that chat loss
   would be expensive.
2. Authority boundaries matter (what must not be touched; what needs re-ask).
3. “Done” must be defensible to someone other than the implementer.
4. Capabilities should interrupt and return, not take over the mission.
5. Failure should show up as `BLOCKED` / `UNVERIFIED`, not as confident vibes.

Decline remains correct for routine, reversible, local, directly checkable,
non-precedential work. Teeth include knowing when **not** to mint a mission.

## Load-bearing unknowns

| Unknown | Why it decides teeth | Closes via |
| --- | --- | --- |
| Does the harness actually load and fire `manifest`? | An unloaded skill is literature | Live harness evidence |
| Will a genuinely independent acceptor rule in practice? | Declared roles are weaker than distinct principals | Principal-bound acceptance evidence in real missions |
| Does the process proof generalize beyond the filesystem path? | One vertical path does not establish broad substrate adequacy | Additional bounded adapters only when a real mission requires them |
| Is a manifest mission more defensible than the same work without it? | Distinctiveness vs ordinary skilled agents is the value claim | Bounded comparative or adversarial trial |
| Will operators invoke it instead of bypassing it? | Adoption is a practical falsifier | Observed use, not README aspiration |

Do not call the skill “proven useful” from definition prose or tests alone.

## Relationship to lookalike seats

- **epistemic-skills / `metacognate`:** decides how much process a claim deserves;
  does not hold mission custody.
- **epistemic-skills / `write-goal`:** authors a completion contract; does not
  dispatch, checkpoint, or revoke.
- **workflow layers (e.g. superpowers):** define how to design, build, debug, and
  verify; pairing is a moment judgment, not a stage table inside `manifest`.

Concise split:

> Goals say what “done” would look like.  
> Epistemics say what may bear load.  
> `manifest` says what the steward is allowed to do next, what must be recorded,
> and when the mission may end.
