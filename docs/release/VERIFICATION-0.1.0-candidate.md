# Verification receipt — 0.1.0 candidate tip

**Subject tip:** `57f37ce39562be13ab59aa0c11d97e26163310f4` (`main` after PR #3)  
**Recorded:** 2026-08-07  
**Actor:** authoring cloud agent (not an independent acceptor)

## Deterministic checks

| Check | Exit | Note |
| --- | --- | --- |
| `python -m unittest discover -s tests -p 'test_*.py' -v` | 0 | 54 tests OK |
| `python -m compileall -q practical_agency tests` | 0 | |
| Parse every committed `*.json` | 0 | 11 files |
| Exactly one `skills/*/SKILL.md` named `manifest` | 0 | |
| Package `__version__` | — | `0.1.0` (unreleased; no tag) |

## Public-content review

Scanned tracked text for absolute home paths, IPv4 literals, credential
assignments, and emails.

| Hit | Classification |
| --- | --- |
| `README.md` / `AGENTS.md` DCO trailer `SternOne <89846440+SternOne@users.noreply.github.com>` | retained — DCO trailer allowlisted by release procedure |

No private repository coordinates, hostnames, tokens, or local absolute paths
were found in the candidate tip.

## Explicitly not established by this receipt

- live harness loading (Cursor / Claude / generic Agent Skills)
- production adapter behavior
- independent adversarial acceptance
- comparative efficacy vs an ordinary skilled agent

## Tag posture

**Do not tag `0.1.0` from this receipt alone.** See the degraded Gauntlet record
under `docs/gauntlet-runs/practical-agency-0.1.0-candidate-2026-08-07/`.
