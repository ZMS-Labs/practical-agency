# Practical Agency

Practical Agency is human-authorized mission control for carrying intent through
durable, coordinated, resumable action.

Its **sole public entry skill is `manifest`**.

Practical Agency does not give an artificial agent independent ends. It extends
the operator's agency through bounded delegation: the operator owns the purpose,
authority, protected state, acceptable costs, amendments, and right to interrupt;
the mission steward preserves those constraints while coordinating capabilities,
execution, continuity, and independent proof.

## Status: deterministic v0.1 kernel

This repository now includes a tested, standard-library-only mission kernel:

- a closed `mission-manifest@1` model and semantic validator;
- append-only, receipted authority amendments and operator-only revocation;
- a closed mission lifecycle with independent acceptance for material completion;
- dynamic capability discovery from current descriptors rather than a copied
  skill inventory;
- bounded capability requests with exact return points;
- one-action execution dispatch with receipted observed effects;
- atomic, content-addressed checkpoints with crash-safe resumption and tamper
  detection;
- live-state contradiction reopening;
- `"helix it"` compatibility as an invocation of `manifest`, not a restored
  routing table; and
- a fail-closed custody bridge for externally verified `watch-commission@1`
  records.

The end-to-end fixture proves that a mission can be approved, dynamically discover
a capability, act once, checkpoint, lose all in-memory state, reload from durable
bytes, detect a live contradiction, repair the result, reject steward
self-acceptance, and complete through an independent acceptor.

### Deliberate limitations

There is **no background service**, daemon, hosted control plane, or autonomous
loop in v0.1. There is **no production execution adapter** and no bundled
scheduler or monitoring provider. The included execution and watch adapters are
protocols exercised with isolated in-process fixtures.

Practical Agency does not authenticate an external receipt merely because its
reference has the right shape. When the upstream commission verifier is absent,
watch custody remains `UNVERIFIED_EXTERNAL_CONTRACT`. No automatic
commission-watch → manifest handoff is claimed.

Live loading in every supported agent harness and the comparative benefit over an
ordinary skilled agent remain unestablished until separate comparative evaluation
and harness-specific verification exist.

## Why this is separate from epistemic skills

Practical Agency owns mission custody: preserving authorized intent, deciding the
current frontier, invoking capabilities, dispatching bounded action, observing
consequences, checkpointing, and resuming.

Epistemic methods retain their own judgments. A mission steward may ask a method
to answer a bounded question, but it cannot rewrite a returned `FAIL`, `NO-GO`,
`BLOCKED`, or `INCONCLUSIVE` result. Material completion requires **independent
acceptance** by an actor that did not perform the material work.

## The public command

Use `manifest` when work is genuinely a mission: multi-step, cross-session,
consequential, shared across agents or humans, or dependent on durable authority,
stop rules, and proof.

Equivalent user intent includes:

```text
manifest this
carry this through
helix it
```

Those phrases enter the same mission semantics. They do not mean “run every
skill.” Applicable capabilities are discovered from the current environment and
invoked only for conditions they own.

Do not invoke `manifest` for a routine one-step task that is directly checkable in
the current session and needs no durable record.

## Mission lifecycle

```text
draft -> active -> paused|blocked|verifying
paused|blocked -> active
verifying -> completed|active|blocked
draft|active|paused|blocked|verifying -- operator revocation --> cancelled
completed|cancelled -> terminal
```

A later live contradiction may reopen a previously completed mission as a new
revision. Conversation memory is never sufficient authority to resume; the
checkpoint is re-anchored to current artifacts and receipts.

See [the mission-manifest field guide](docs/mission-manifest.md) for the complete
record structure.

## Commission-watch boundary

`commission-watch` owns whether an external observation claim is honestly
specified, commissioned, and proof-fired. The external observer—not this skill or
`manifest`—owns persistence between sessions.

Practical Agency may retain a record only through a supplied upstream verifier.
It may then coordinate an authorized adapter, preserve receipts, disable on
revocation, or reopen a mission when a real crossing event arrives. It may never
synthesize `PROVEN`, weaken the upstream oracle, or reinterpret
`handoff.on_crossing` as mission custody.

The example mission deliberately begins with no execution substrate and records
`UNVERIFIED_EXTERNAL_CONTRACT`; it does not imply an installed watch.

## Repository layout

```text
skills/manifest/SKILL.md              sole public skill
practical_agency/                     deterministic mission kernel
contracts/                            JSON Schema carriers
roles/                                steward and independent acceptor contracts
adapters/                             adapter boundary documentation
examples/                             validated mission examples
tests/                                deterministic unit and end-to-end proofs
```

The root `skills/manifest/SKILL.md` is canonical. Plugin metadata must point to or
auto-discover that same root directory; no second independently editable skill
tree is permitted.

## Run the proof suite

Python 3.12 or newer is required.

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
python .github/scripts/check_repo.py
```

The project has no runtime dependencies outside the Python standard library.

## Minimal kernel use

```python
from pathlib import Path

from practical_agency.checkpoint_store import CheckpointStore
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import transition
from practical_agency.validation import load_manifest

mission = load_manifest(Path("examples/minimal-mission.json"))
active = transition(
    mission,
    "active",
    actor_ref="operator:example",
    evidence_ref="approval://example",
    reason="mission approved",
)
CheckpointStore(Path(".mission-state")).save(active)
```

This creates durable mission state. It does not create an unattended agent.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
