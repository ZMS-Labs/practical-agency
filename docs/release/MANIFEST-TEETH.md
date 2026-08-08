# What would give `manifest` real teeth?

Status: **operator-facing definition** under mission `climb-pa-0-1` (approved
2026-08-08). This is not a claim that teeth already exist in production use.

`manifest` has teeth only when it changes what an agent **may do**, what may
count as **done**, and what **survives** when the chat dies — in ways a goal
note, a todo list, or an ordinary skilled agent does not.

## Not teeth (already exists / easy to fake)

| Lookalike | Why it is not enough |
| --- | --- |
| Goal / `write-goal` completion contract | Names desired state and proof; does not custody authority, dispatch, or resume-against-live-state |
| Plan / todo / checklist | Structures work; rarely binds revocation, protected state, or independent acceptance |
| Prompt prose (“preserve the user’s intent”) | Evaporates under compaction; cannot refuse an illegal transition |
| In-process fixtures alone | Prove the kernel; do not prove the skill fires or reaches the world |
| Router / skill inventory / “helix table” | Ceremony and drift; Practical Agency deliberately refuses this seat |

If removing `manifest` would not change stop rules, completion rules, or
post-interruption defensibility, it has no teeth.

## Teeth = four powers

### 1. Negative power — it can stop you

Permissions are allowlists. Protected state and costs are first-class.
Revocation cancels consequential progress. The steward may not invent ends or
rewrite the operator’s instruction.

**Falsifier:** after revocation or outside permissions, consequential work still
proceeds “because it was useful.”

### 2. Continuity power — it outlives the chat

`mission-manifest@1` plus atomic checkpoints are the contract of record. Resume
re-anchors to live artifacts and receipts; contradictions reopen. Memory and
summaries are untrusted until checked.

**Falsifier:** a new session continues from a chat summary while a checkpoint
disagrees, and nobody notices.

### 3. World power — intent can touch reality under authority

At least one bounded adapter performs a consequential authorized effect and
returns an **external durable receipt**. In-memory fixtures do not count.
Missing substrate becomes visible `BLOCKED`, not silent prose success.

**Falsifier:** “mission complete” with only narrative artifacts for a claim that
required an external effect.

This is the gap between a custody kernel and **`1.0.0` / v1** (first
operator-useful major). A bounded filesystem artifact adapter is an early world
path; it is not by itself v1. Operator direction (2026-08-08): defer `0.1.0` tag
ceremony and keep building teeth. See [VERSIONING.md](VERSIONING.md).

### 4. Proof power — the worker cannot bless the work

Material completion requires a declared independent acceptor. Adapter success is
not mission completion. Watch adapter success is not `PROVEN`.

**Falsifier:** the same actor who did the work marks the mission `completed`.

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

## Load-bearing unknowns (must know to ensure teeth)

| Unknown | Why it decides teeth | Closes via |
| --- | --- | --- |
| Does the harness actually load and fire `manifest`? | Unloaded skill is literature | Live harness rows (P2-HARNESS-LOAD) |
| Will an independent acceptor rule in practice? | Without them, completion collapses to self-certify | Release acceptor + real missions |
| Can one bounded adapter emit an external durable receipt? | Without world power, custody is theater | `1.0.0` adapter gate |
| After interruption, is a manifest mission more defensible than the same work without it? | Distinctiveness vs ordinary skilled agent | Bounded comparative / adversarial trial (later; not required to *define* teeth) |
| Will operators invoke it instead of bypassing when work gets consequential? | Adoption falsifier | Observed use, not README aspiration |

## Minimum ladder for “real teeth” in the field

```text
0.1.0 tagged     → custody teeth exist as a support point (fixtures + honest limits)
live harness     → the skill can fire where the operator works
1.0.0            → world teeth: one receipted authorized effect path
later evidence   → comparative defensibility (optional for 1.0 honesty; required
                   before claiming superiority)
```

Do not call the skill “proven useful” from definition prose or unit tests alone.

## Relationship to lookalike seats

- **epistemic-skills / `metacognate`:** decides how much process a claim deserves;
  does not hold mission custody.
- **epistemic-skills / `write-goal`:** authors a completion contract; does not
  dispatch, checkpoint, or revoke.
- **workflow layers (e.g. superpowers):** how to design/build/debug; pairing is a
  moment judgment, not a stage table inside `manifest`.

Concise split:

> Goals say what “done” would look like.  
> Epistemics say what may bear load.  
> `manifest` says what the steward is allowed to do next, what must be recorded,
> and when the mission may end.
