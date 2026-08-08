# Verification receipt — 0.1.0 climb tip

**Subject branch:** `cursor/climb-0-1-a955`  
**Base kernel:** PR #4 hardened tip (`de5cdf4`) with `land-pa-0-1` independent
PASS for kernel-candidate scope only  
**Docs layer:** VERSIONING + RELEASE-1.0.0-CRITERIA cherry-picked onto that tip  
**Recorded:** 2026-08-08  
**Actor:** authoring cloud agent (not an independent acceptor)

## Deterministic checks (this session)

| Check | Exit | Note |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 0 | 97 tests OK, 1 skipped (pinned upstream suite not fetched in this shell) |
| `python3 .github/scripts/check_package.py` | 0 | description_bytes=402/420 |
| `python3 .github/scripts/check_contracts.py` | 0 | 7 schemas, 2 mission examples |
| `python3 .github/scripts/check_public_content.py` | 0 | |

CI on PR #4 previously recorded 101 OK with pinned `epistemic-skills@6e26484a`
(`ci:run:31230365670`). Re-run full pinned CI on the climb PR head before tag.

## Ladder posture

| Rung | Status |
| --- | --- |
| `0.1.0` custody kernel | candidate; tag blocked on open P2 |
| `1.0.0` operator-useful major | criteria only; not started as implementation |

See [VERSIONING.md](VERSIONING.md) and
[RELEASE-1.0.0-CRITERIA.md](RELEASE-1.0.0-CRITERIA.md).

## Harness

| Harness | Tier | Evidence |
| --- | --- | --- |
| Cursor (cloud agent workspace) | `structural-archive-only` | [harness-observations/cursor-cloud-2026-08-08.md](harness-observations/cursor-cloud-2026-08-08.md) |
| Cursor (desktop plugin install) | unmet | |
| Claude plugin | unmet | |
| Generic Agent Skills layout | unmet | |

## Independent acceptance

| Scope | Status |
| --- | --- |
| 0.1 kernel-candidate (`land-pa-0-1`) | PASS at `de5cdf4` — does not authorize tag |
| 0.1 release/tag on climb tip | unmet |

## Tag posture

**Do not tag `v0.1.0` from this receipt alone.** Close or explicitly waive
P2-HARNESS-LOAD and P2-INDEPENDENT-ACCEPT first. A waiver is not independence.
