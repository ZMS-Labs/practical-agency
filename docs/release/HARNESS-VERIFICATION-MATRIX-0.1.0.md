# Harness verification matrix — Practical Agency 0.1.0 climb tip

**Purpose:** discharge P2-HARNESS-LOAD with honest tiers. A tier records what was
actually exercised. It does not upgrade a blocked live check into a pass.

**Subject tip:** record the exact SHA in the observation that freezes the climb
PR head (see harness-observations/).

## Tier vocabulary

| Tier | Meaning |
| --- | --- |
| `LIVE` | Harness install path loaded exactly one skill `manifest` from this candidate with byte-exact description and invocation intents present |
| `DETERMINISTIC` | Repository CI / stdlib checks prove packaging surfaces and contracts |
| `STRUCTURAL` | Manifest/path/layout inspected; load behavior not exercised |
| `LIVE_BLOCKED_EXTERNAL` | Live harness/session panel unavailable here; limitation named |

## Matrix

| Harness | Install source | Reload / cache | Duplicate-install risk | Verification tier | Evidence |
| --- | --- | --- | --- | --- | --- |
| Cursor | `.cursor-plugin/` + Agent Skills project install via `npx skills add <checkout> --skill manifest` → `.agents/skills/manifest` | Fresh agent task / reload after install | Do not also duplicate into a second skills root | `DETERMINISTIC` + `LIVE` (install inventory) / Customize→Skills panel dump still `LIVE_BLOCKED_EXTERNAL` | `check_package.py`, `check_harness_surfaces.py`, `harness-observations/agent-skills-npx-2026-08-08.md` |
| Generic Agent Skills | Same `.agents/skills/manifest` layout (stdlib materialize or `npx skills add`) | Harness-specific | Must not stack on a conflicting native copy | `LIVE` | Materialize receipt + npx install observation |
| Claude | `.claude-plugin/plugin.json` → `./skills/` | Fresh task after install | Native plugin **or** copied skills — never both | `DETERMINISTIC` + `LIVE_BLOCKED_EXTERNAL` | Plugin metadata points at `./skills/`; live Claude load not exercised in this cloud agent |

## Closing rule for P2-HARNESS-LOAD

P2-HARNESS-LOAD may close when:

1. every harness named in installation docs has a row above; and
2. Cursor and Generic Agent Skills each have a `LIVE` install-inventory receipt
   for the frozen tip (panel dump may remain `LIVE_BLOCKED_EXTERNAL` if named); and
3. Claude remains at worst `DETERMINISTIC` + `LIVE_BLOCKED_EXTERNAL` while the
   README does not claim live Claude loading.

Owner waiver is still required before treating `LIVE_BLOCKED_EXTERNAL` rows as
irrelevant to a conforming tag if installation docs claim those harnesses as
fully verified.
