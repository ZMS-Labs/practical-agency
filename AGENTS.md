# Agent instructions

Practical Agency is a deterministic mission-control kernel with exactly one
public skill, `manifest`.

## Invariants

- Preserve operator instructions verbatim; amendments are append-only.
- Do not add a second public skill for resume, checkpoint, reconcile, dispatch,
  commission, or closure. Those are internal mission operations.
- Do not hard-code an inventory of workflow or epistemic capabilities.
- A mission steward never self-certifies material completion.
- No background, runtime, scheduler, or persistence claim is valid without an
  external durable receipt.
- `watch-commission@1` remains governed by its upstream semantic verifier.
  Practical Agency may retain a verified record but may not duplicate or weaken
  that verifier.
- No production adapter may execute arbitrary shell commands by default.
- Keep public content free of private infrastructure, credentials, hostnames,
  local absolute paths, and non-public repository coordinates.

## Development discipline

1. Write the failing test first and verify the expected failure.
2. Implement only enough behavior to pass it.
3. Run the focused test and the full suite.
4. Preserve exact named refusal codes and closed state transitions.
5. Sign every commit with a DCO trailer matching the commit author.

## Required verification

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
python .github/scripts/check_contracts.py
python .github/scripts/check_package.py
python .github/scripts/check_public_content.py
```
