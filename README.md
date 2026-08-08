# Practical Agency

Practical Agency is human-authorized mission control for carrying intent through
durable, coordinated, resumable action.

Its sole public entry skill is `manifest`.

Practical Agency does not give an artificial agent independent ends. It extends
the operator's agency through bounded delegation: the operator owns the purpose,
authority, protected state, acceptable costs, and right to interrupt; the system
preserves those constraints while coordinating workflow, epistemic discipline,
execution substrates, continuity, and independent proof.

## Status

Version 0.1 is a deterministic, standard-library mission kernel plus a portable
Agent Skill. It is **not a daemon**, hosted service, scheduler, autonomous
background actor, or source of independent machine goals.

The repository exercises deterministic mission custody, bounded authority, atomic
checkpoints, forward-compatible dynamic capability discovery, revision-bound
events and proposals, exact return points, crash-visible receipt journaling,
fail-closed live-state reconciliation, evidence-bearing independent completion,
and pinned upstream interoperability in isolated tests. These tests verify
structured provenance and recorded clearance; they do not prove unrestricted
natural-language entailment.

There is **no general-purpose shell execution adapter**. A bounded filesystem artifact adapter can write allowlisted text artifacts with on-disk
receipts (`practical_agency.filesystem_artifact`). That is not v1 readiness.
Cursor/Generic Agent Skills install inventory is LIVE for the climb tip
(see `docs/release/HARNESS-VERIFICATION-MATRIX-0.1.0.md`);
Customize→Skills panel and Claude live load remain unverified.
comparative benefit over an ordinary capable agent is also unestablished
until a controlled evaluation exists. Operator direction: defer `0.1.0` tag
ceremony; invest in teeth toward v1.

`1.0.0` is **reserved**, not imminent. It means the first operator-useful major:
authorized intent installable in a declared harness, advanced through at least
one bounded adapter with an external durable receipt, resumable from
checkpoints, and closable only by an independent acceptor. See
[docs/release/VERSIONING.md](docs/release/VERSIONING.md) and
[docs/release/RELEASE-1.0.0-CRITERIA.md](docs/release/RELEASE-1.0.0-CRITERIA.md).
Tagging or accepting `0.1.0` does not satisfy those criteria.

## Conceptual stack

| Layer | Owns |
| --- | --- |
| Operator | Purpose, authority, protected state, cost, revocation |
| Practical Agency | Mission custody, continuity, capability coordination, checkpoints |
| Workflow methods | How implementation, debugging, and verification proceed |
| Epistemic methods | What makes a claim, gate, observation, or decision trustworthy |
| External substrates | Actual execution, scheduling, monitoring, and notification |

The project doctrine is **bounded delegated agency**. The acting role is the
**mission steward**. The durable artifact is `mission-manifest@1`.

## Quick start

1. Install or expose [`skills/manifest/SKILL.md`](skills/manifest/SKILL.md) to the
   harness.
2. Invoke `manifest` for a multi-step, consequential, resumable, or cross-agent
   outcome. “Helix it” is accepted as compatibility intent for the same mission
   driver.
3. Create and validate a mission manifest from
   [`examples/minimal-mission.json`](examples/minimal-mission.json).
4. Save revision 1 before approval, then advance the mission through closed
   events and atomic checkpoints.
5. Complete material work only through the declared independent acceptor.

A routine, reversible, directly checkable one-step task should not mint a mission.

## Deterministic kernel

The Python package contains:

- strict `mission-manifest@1` validation and canonical JSON;
- authority checks for permissions, protected state, costs, escalation, and
  revocation;
- a closed mission state machine with proof-ready, evidence-bearing independent
  acceptance;
- hash-bound atomic checkpoint storage;
- live-state reconciliation that invalidates stale completion/gate artifacts,
  opens one bounded repair frontier, and requires fresh observation before
  verification;
- dynamic capability discovery from immediate `SKILL.md` children, without a
  copied member list;
- exact request/result/receipt and return-point binding;
- one-action coordination, with load-bearing blockers permitting only the exact
  recorded remediation action; and
- an adapter boundary that accepts `watch-commission@1` only through its
  originating verifier.

Run the package-local deterministic gate:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests .github/scripts
python .github/scripts/check_contracts.py
python .github/scripts/check_package.py
python .github/scripts/check_harness_surfaces.py
python .github/scripts/check_public_content.py
```

The permanent CI gate additionally checks out `epistemic-skills` at immutable
revision `6e26484a9cae7629b233734fe5121137ba9168a8`. It requires the actual
commission-watch semantic verifier and example corpus, and dynamically discovers
every pinned skill descriptor without maintaining a copied member inventory.

## Commission-watch boundary

Practical Agency does not become the observer. The upstream commission-watch
discipline defines and proves the observation claim; an external mechanism does
the actual between-session watching. Practical Agency may retain a validated
commission, coordinate an authorized adapter, preserve receipts, and record a
receipted crossing handoff. A crossing cannot rewrite the frontier or reopen a
completed mission; only a revision-bound replan proposed against the crossing and
applied by the mission steward may do that.

Pinned interoperability tests establish that:

- the actual upstream accepted/rejected corpus keeps the same oracles when passed
  through Practical Agency;
- a `DECLARED` commission prepared by the Practical Agency adapter boundary is
  accepted by the upstream verifier as `BLOCKED: KILL_SWITCH_UNPROVEN`; and
- the upstream contract rejects `manifest` as a value of
  `handoff.on_crossing`.

That proves carrier/verifier compatibility at one immutable revision. It does
**not** authenticate receipt references, commission a production observer, admit
a production adapter, or create an automatic `watch` → `manifest` route.
Post-crossing method selection remains external to Practical Agency. The handoff
contains a bounded condition, expected output contract, and return point rather
than a named skill route.

## Repository map

```text
skills/manifest/                  sole public skill
practical_agency/                 deterministic mission kernel
contracts/                        portable JSON Schema carriers
roles/                            steward and independent acceptor contracts
adapters/                         optional execution boundary documentation
examples/                         valid mission examples
tests/                            deterministic, integration, and end-to-end fixtures
```

## Relationship to epistemic-skills

[`epistemic-skills`](https://github.com/ZMS-Labs/epistemic-skills) governs what may
honestly bear epistemic load. Practical Agency governs how an operator-authorized
mission preserves continuity and advances through bounded action. Neither package
absorbs the other's methods or verdicts.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
