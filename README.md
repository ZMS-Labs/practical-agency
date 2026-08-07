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

The repository proves deterministic mission custody, bounded authority, atomic
checkpoints, dynamic capability discovery, request/receipt binding, exact return
points, crash recovery, fail-closed live-state reconciliation, evidence-bearing
independent completion, and pinned commission-contract interoperability in
isolated tests.

There is **no production external execution adapter** in v0.1; live harness loading remains unverified
until each packaging surface is exercised against its exact installed revision;
comparative benefit over an ordinary capable agent is also unestablished until a
controlled evaluation exists.

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
python .github/scripts/check_public_content.py
```

The permanent CI gate additionally checks out the commission-watch contract at
immutable `epistemic-skills` revision
`6e26484a9cae7629b233734fe5121137ba9168a8` and requires its actual semantic
verifier and example corpus during the test run.

## Commission-watch boundary

Practical Agency does not become the observer. The upstream commission-watch
discipline defines and proves the observation claim; an external mechanism does
the actual between-session watching. Practical Agency may retain a validated
commission, coordinate an authorized adapter, preserve receipts, and reopen a
mission when a receipted crossing arrives.

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
Post-crossing `triage` and `decision-ledger` classification remains separate from
mission custody.

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
