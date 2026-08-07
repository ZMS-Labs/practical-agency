# Agent notes — Practical Agency

## Project identity

- Repository / project: **practical-agency** / **Practical Agency**
- Sole public skill: **`manifest`** at `skills/manifest/SKILL.md`
- Doctrine: bounded delegated agency
- Distribution name: `zms-practical-agency` (PyPI-safe); do not claim an unscoped package name

## Hard rules

- Do not create additional public skills for resume, checkpoint, reconcile, dispatch, commission, or close.
- Preserve operator-authored instructions and amendments verbatim and append-only.
- Material completion requires an independent acceptor; never self-certify.
- No runtime, scheduler, or persistence claim without an external durable receipt.
- Stdlib-only deterministic core; adapter dependencies remain optional and isolated.
- Every production behavior change follows RED → GREEN → REFACTOR.
- Every commit carries `Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>`.
- Public content must not expose private repository names, local absolute paths, credentials, hostnames, or estate topology.

## Current status

`0.1.0` metadata describes an **unreleased seed**. Do not call this a deterministic
mission kernel until the seed-adoption plan Tasks 2–9 and independent acceptance
pass. It is neither a daemon, hosted service, nor autonomous background actor.

## Commands

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
```

## Repository settings (operator)

Normalize when admin rights are available:

- projects: disabled
- wiki: disabled
- squash merge: enabled
- merge commits: disabled
- rebase merge: disabled
- auto-merge: disabled initially
- delete head branches: enabled
