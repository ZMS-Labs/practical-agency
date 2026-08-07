# Mission manifest — field guide (v0)

The **mission manifest** is the durable artifact for [Practical Agency](https://github.com/ZMS-Labs/practical-agency). It binds **bounded delegated agency**: what a mission steward may do, where evidence goes, and when work must stop.

## Where it lives

Choose one authoritative path per mission and record it in the manifest header:

- **Repo mission** — `docs/missions/<mission-id>.md` or `.missions/<mission-id>.md`
- **Project mission** — `MISSION.md` at the project root (single active mission only)
- **Fleet mission** — path declared in the controlling repo's governance docs

Never fork the manifest across two locations. Link from chat; do not duplicate authority.

## Template

Copy and fill:

```markdown
---
mission_id: <kebab-case-id>
status: draft | active | hold | complete | cancelled
sovereign: <name or role>
steward: <agent or team>
opened: <ISO-8601 date>
updated: <ISO-8601 date>
---

# Mission: <short title>

## Intent

<What the sovereign wants — outcome, not task list.>

## Scope

### In

- …

### Out

- …

### Environments

- …

## Authorization

| Class | Steward may | Requires re-approval |
| --- | --- | --- |
| Read / observe | … | … |
| Reversible local edit | … | … |
| Consequential / irreversible | … | always |

## Evidence

| Claim | Oracle / location |
| --- | --- |
| Progress | … |
| Completion | … |

## Stop and hold

- **Hold if:** …
- **Stop if:** …
- **Escalate if:** …

## Log

Reverse-chronological notes; material decisions only.

- <date> — …
```

## Status semantics

| Status | Meaning |
| --- | --- |
| `draft` | Manifest under construction; no consequential execution. |
| `active` | Steward may execute within authorization. |
| `hold` | Blocked; steward must not expand scope until cleared. |
| `complete` | Outcome accepted or explicitly abandoned with record. |
| `cancelled` | Sovereign withdrew mission; no further execution. |

## Completion block

When closing, append:

```markdown
## Completion

- **Result:** …
- **Evidence:** …
- **Not done:** …
- **Follow-ups:** …
```

## Versioning

Bump `updated` on every material edit. For long missions, consider git tags or manifest filename versioning (`mission-id-v2.md`) instead of silent overwrite.
