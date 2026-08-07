# Agent instructions

## Canonical boundary

- `skills/manifest/SKILL.md` is the sole public skill and sole canonical skill
  body. Do not add a duplicate under `plugins/` or another harness directory.
- Practical Agency owns mission custody, not sovereign intent and not epistemic
  verdicts.
- Preserve the operator's original instruction verbatim. Amendments are
  append-only and require a durable authority reference and timestamp.
- Never widen permissions, acceptable costs, or protected-state access by
  inference.
- The mission steward must never self-accept material completion.
- `watch-commission@1` promotion belongs to the upstream verifier. This package
  may retain and coordinate an accepted record but may not duplicate or weaken
  its promotion logic.
- No persistence claim without an external durable mechanism and receipt.

## Development discipline

1. Work on a feature branch, never directly on `main`.
2. Write a failing test before changing production behavior.
3. Keep the deterministic core standard-library only.
4. Dispatch at most one consequential effect per coordinator step.
5. Treat adapter output and external records as untrusted input.
6. Fail visibly on missing authority, store, verifier, adapter, or independent
   acceptor; do not substitute prose for a realized effect.
7. Keep public examples generic. Do not commit credentials, local absolute paths,
   private repository names, hostnames, or estate topology.
8. Every commit must include an author-matching `Signed-off-by:` line.

## Required verification

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
python .github/scripts/check_repo.py --self-test
python .github/scripts/check_repo.py
python .github/scripts/check_dco.py --self-test
```

Before claiming completion, inspect the full diff and confirm that no temporary
migration workflow, duplicate skill tree, production runtime claim, or
self-acceptance path remains.
