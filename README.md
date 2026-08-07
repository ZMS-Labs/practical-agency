# Practical Agency

Practical Agency is human-authorized mission control for carrying intent through
durable, coordinated, resumable action.

Its sole public entry skill is `manifest`.

Practical Agency does not give an artificial agent independent ends. It extends
the operator's agency through bounded delegation: the operator owns the purpose,
authority, protected state, acceptable costs, and right to interrupt; the system
preserves those constraints while coordinating workflow, epistemic discipline,
execution substrates, continuity, and independent proof.

| Concept | Name |
| --- | --- |
| Project | Practical Agency |
| Public skill | `manifest` |
| Doctrine | Bounded delegated agency |
| Role | Mission steward |
| Artifact | Mission manifest |
| Distribution | `zms-practical-agency` |

Licensed under [GPL-3.0-or-later](LICENSE).

## Current status

`0.1.0` remains an **unreleased** version. This branch adds a stdlib
deterministic mission kernel (`mission-manifest@1`, authority/transitions,
atomic checkpoints, dynamic capability discovery, bounded coordinator) and
upgrades the sole public `manifest` skill. It is still **not** a production
runtime: no daemon, hosted service, autonomous background actor, or production
execution adapter is claimed. Live harness loading and comparative efficacy
remain unverified until exercised per harness.

## What this is

Most agent stacks optimize *execution*: plans, tools, and verification loops.
Practical Agency optimizes *delegation*: who may act, on what scope, for how
long, with what stop rules, and what durable record survives when the chat ends.

The steward does not replace the sovereign (the human). It holds continuity for a
**mission** — a bounded slice of work with explicit authorization — and refuses
to expand agency beyond what the manifest records.

## Quick start

1. Install the package for your harness (see [Installation](#installation)).
2. When a task is more than a single reversible edit — multi-step, cross-session,
   consequential, or shared across agents — invoke **`manifest`** before
   expanding scope.
3. Author or update a **mission manifest** at the mission's authoritative sink
   (usually the repo or project root). Treat the manifest as the contract of
   record; chat is not.

## The `manifest` skill

The only published skill in this package is [`manifest`](skills/manifest/SKILL.md).
It tells a mission steward how to:

- open, resume, or close a mission without silent scope creep;
- bind human authorization to concrete allowed actions;
- persist decisions and stop conditions in a mission manifest;
- hand off or pause without losing defensibility.

## Mission manifest (artifact)

A mission manifest is a small, version-controlled document that answers:

- **Intent** — what outcome the sovereign wants, in their words where possible.
- **Scope** — inclusions, exclusions, and environments touched.
- **Authorization** — what the steward may do without re-asking; what requires fresh consent.
- **Evidence** — where proof of progress and completion must land.
- **Stop / hold** — conditions that pause or end the mission.

See [`docs/mission-manifest.md`](docs/mission-manifest.md) for the v0 field guide
and template. The target machine-checkable carrier is `mission-manifest@1`.

## Installation

### Cursor

Add this repository as a plugin source, or copy `skills/manifest/` into your
project's skills directory. Reload the session so skill discovery runs.

### Generic Agent Skills layout

```text
your-project/
  .agents/skills/manifest/   # or your harness's skills root
    SKILL.md
```

Point your harness at the skill root per its documentation.

## Relationship to other ZMS packages

- **[epistemic-skills](https://github.com/ZMS-Labs/epistemic-skills)** — what must be *true* before a claim bears load (including commission-watch).
- **Practical Agency** — what a steward is *allowed* to do while pursuing a mission, and what must be *recorded* so work survives compaction.

Use both when missions are consequential and claims must be defensible.
`manifest` may custody a validated `watch-commission@1` record when installed
with a compatible adapter; it must not promote commission state itself.

## Developing

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
```

Deterministic mission custody is proven by the in-process end-to-end fixture.
No production external execution adapter is included yet. No background service
is claimed. Live harness loading is unverified until tested in each packaged
harness. End-to-end mission benefit over an ordinary skilled agent remains
unestablished until comparative evaluation exists.

Follow the [DCO](https://developercertificate.org/) sign-off on commits
(`Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>` for
maintainer commits on this program).

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
