---
mission_id: env-smoke-mission
status: draft
sovereign: environment-setup
steward: cloud-agent
opened: 2026-08-07
updated: 2026-08-07
---

# Mission: Environment smoke validation

## Intent

Prove the Practical Agency package validates and mission manifest paths are writable.

## Scope

### In

- Skill validation via skills-ref
- Mission manifest template under docs/missions/

### Out

- Production deployments

### Environments

- Cloud Agent development VM

## Authorization

| Class | Steward may | Requires re-approval |
| --- | --- | --- |
| Read / observe | Repository and skill files | — |
| Reversible local edit | Demo mission manifest only | — |
| Consequential / irreversible | None | always |

## Evidence

| Claim | Oracle / location |
| --- | --- |
| Progress | scripts/demo-mission-flow.sh output |
| Completion | This file plus validate exit 0 |

## Stop and hold

- **Hold if:** skills-ref validate fails
- **Stop if:** required tooling missing after install
- **Escalate if:** manifest skill frontmatter invalid

## Log

- 2026-08-07 — Created for Cloud Agent environment smoke test.
