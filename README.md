# Practical Agency

**Human-authorized mission control for durable agentic work.**

Practical Agency is a harness-agnostic [Agent Skills](https://agentskills.io/specification) package from [ZMS Labs](https://github.com/ZMS-Labs). It gives agents a **mission steward** role under the doctrine of **bounded delegated agency**, with the **mission manifest** as the durable artifact that binds intent, scope, and authorization across sessions and surfaces.

| Concept | Name |
| --- | --- |
| Project | Practical Agency |
| Public skill | `manifest` |
| Doctrine | Bounded delegated agency |
| Role | Mission steward |
| Artifact | Mission manifest |

Licensed under [GPL-3.0-or-later](LICENSE).

## What this is

Most agent stacks optimize *execution*: plans, tools, and verification loops. Practical Agency optimizes *delegation*: who may act, on what scope, for how long, with what stop rules, and what durable record survives when the chat ends.

The steward does not replace the sovereign (the human). It holds continuity for a **mission** — a bounded slice of work with explicit authorization — and refuses to expand agency beyond what the manifest records.

## Quick start

1. Install the package for your harness (see [Installation](#installation)).
2. When a task is more than a single reversible edit — multi-step, cross-session, consequential, or shared across agents — invoke **`manifest`** before expanding scope.
3. Author or update a **mission manifest** at the mission's authoritative sink (usually the repo or project root). Treat the manifest as the contract of record; chat is not.

## The `manifest` skill

The only published skill in this package is [`manifest`](skills/manifest/SKILL.md). It tells a mission steward how to:

- open, resume, or close a mission without silent scope creep;
- bind human authorization to concrete allowed actions;
- persist decisions and stop conditions in a mission manifest;
- hand off or pause without losing defensibility.

## Mission manifest (artifact)

A mission manifest is a small, version-controlled document (Markdown with optional YAML front matter) that answers:

- **Intent** — what outcome the sovereign wants, in their words where possible.
- **Scope** — inclusions, exclusions, and environments touched.
- **Authorization** — what the steward may do without re-asking; what requires fresh consent.
- **Evidence** — where proof of progress and completion must land.
- **Stop / hold** — conditions that pause or end the mission.

See [`docs/mission-manifest.md`](docs/mission-manifest.md) for the v0 field guide and template.

## Installation

### Cursor

Add this repository as a plugin source, or copy `skills/manifest/` into your project's skills directory. Reload the session so skill discovery runs.

### Generic Agent Skills layout

```text
your-project/
  .agents/skills/manifest/   # or your harness's skills root
    SKILL.md
```

Point your harness at the skill root per its documentation.

## Relationship to other ZMS packages

- **[epistemic-skills](https://github.com/ZMS-Labs/epistemic-skills)** — what must be *true* before a claim bears load.
- **Practical Agency** — what a steward is *allowed* to do while pursuing a mission, and what must be *recorded* so work survives compaction.

Use both when missions are consequential and claims must be defensible.

## Developing

This repository is early. Issues and PRs welcome. Follow the [DCO](https://developercertificate.org/) sign-off on commits.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
