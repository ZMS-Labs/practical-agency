# Harness observation — npx skills add (Cursor + Generic Agent Skills)

```text
source revision: fddd94252b3550975d439d09710294a864aa73b8
installed path: /tmp/pa-skills-live/.agents/skills/manifest (probe outside product tree)
loaded skill count: 1
loaded skill name: manifest
loaded description present and exact: True
"manifest this" invocation accepted: yes (description/discovery contract; intents present)
"helix it" compatibility intent accepted: yes (description/discovery contract; intents present)
cache/reload behavior: new probe directory; skills CLI copied files; no prior cache
verification tier: LIVE
observer: agent:implementer
date: 2026-08-08
```

## Receipt

```json
{
  "cache_reload_behavior": "new probe directory; skills CLI copied files; no prior cache",
  "date": "2026-08-08",
  "description_bytes": 402,
  "harness": "Cursor + Generic Agent Skills (npx skills add)",
  "helix_it_intent_in_description": true,
  "installed_path": "/tmp/pa-skills-live/.agents/skills/manifest (probe outside product tree)",
  "limits": [
    "Customize/Skills panel dump not available in this cloud agent",
    "Invocation accepted at description/discovery contract level; not a separate GUI click test",
    "Probe directory is outside the product tree so package rglob stays one-skill"
  ],
  "loaded_description_present_and_exact": true,
  "loaded_skill_count": 1,
  "loaded_skill_name": "manifest",
  "loaded_skill_names": [
    "manifest"
  ],
  "manifest_this_intent_in_description": true,
  "observer": "agent:implementer",
  "schema": "practical-agency-harness-observation@1",
  "source_revision": "fddd94252b3550975d439d09710294a864aa73b8",
  "verification_tier": "LIVE"
}
```

## Limits

- Customize → Skills panel dump remains unavailable in this cloud agent (`LIVE_BLOCKED_EXTERNAL` for that panel only).
- Does not prove Claude live loading.
- Does not authorize tag by itself; independent release accept remains open.
