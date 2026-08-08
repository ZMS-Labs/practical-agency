# PR #7 boundary-hardening implementation plan

> Execute with Superpowers test-driven development. Each task begins with a failing boundary test, observes the failure in GitHub Actions, implements the minimum coherent fix, and reruns the focused and full verification suites. Do not merge PR #7.

**Goal:** Make the architectural guarantees claimed by PR #7 enforceable against stale, forged, malformed, replayed, and interrupted inputs.

**Base:** PR #7 head `859ef0cae43dba941dcb545a094bcbb81583a2a8`  
**Working branch:** `chatgpt/pr7-boundary-hardening-20260808`

## Task 1: Establish dynamic-discovery interoperability

**Files**
- Modify: `practical_agency/capability_discovery.py`
- Modify: `tests/test_capability_discovery.py`
- Modify: `.github/workflows/ci.yml`

**Red tests**
- A valid descriptor containing unknown metadata such as `hands-to` remains available.
- A malformed recognized authority-sensitive field still degrades.
- When `PRACTICAL_AGENCY_UPSTREAM_SKILLS_DIR` is present, every pinned upstream descriptor is discovered dynamically with no copied member list.

**Implementation**
- Preserve opaque unknown metadata.
- Validate known fields strictly.
- Export the pinned skills directory to tests in CI.

## Task 2: Introduce revision-bound, replay-safe event envelopes

**Files**
- Modify: `practical_agency/state_machine.py`
- Modify: `practical_agency/validation.py`
- Modify: `contracts/mission-event.schema.json`
- Modify: `contracts/mission-manifest.schema.json`
- Modify: `tests/helpers.py`
- Modify all tests/call sites constructing `MissionEvent`

**Red tests**
- Cross-mission event refusal.
- Stale revision refusal.
- Duplicate event ID refusal.
- Runtime event serialization validates against `mission-event@1`.

**Implementation**
- Add the complete envelope and a live-manifest event factory.
- Reject envelope failures before mutation.
- Persist processed IDs in continuity after successful apply.
- Add event kinds required by watcher and execution-receipt recording.

## Task 3: Bind mission-OS proposals and sole-writer crossing flow

**Files**
- Modify: `practical_agency/mission_os.py`
- Modify: `practical_agency/state_machine.py`
- Modify: `practical_agency/watch_commission.py`
- Modify: `tests/test_mission_os.py`
- Modify: `tests/test_watch_commission.py`
- Modify: `tests/test_state_machine.py`

**Red tests**
- Proposal mission/base-revision/hash tampering is refused.
- Fabricated contradiction or basis refs are refused.
- Watch crossing records an observation/handoff but leaves frontier, next action, status, and revision unchanged until an apply event.
- Crossing payload contains no named skill route.

**Implementation**
- Canonically bind proposals.
- Validate resolvable basis records and explicit replace ranges.
- Replace direct watch mutation with an observation/handoff result.
- Record applied-frontier identity and hash in decisions.

## Task 4: Enforce applied-frontier and dispatch authority at the effect boundary

**Files**
- Modify: `practical_agency/coordinator.py`
- Modify: `practical_agency/authority.py` as needed
- Modify: `practical_agency/filesystem_artifact.py`
- Modify: `tests/test_coordinator.py`

**Red tests**
- Capability interruption before apply is refused.
- Caller cannot disable the apply gate.
- Manually forged dispatch decision is refused.
- Request mutation after coordination is refused.
- Unauthorized request is refused again at dispatch.
- Adapter/capability mismatch is refused.
- Invalid return-point index is refused in emit, coordinate, and result application.

**Implementation**
- Make apply verification unconditional and live-state-bound.
- Carry and verify canonical request hash.
- Revalidate/re-authorize immediately before dispatch.
- Require stable adapter identity/capability binding.
- Centralize strict return-point validation.

## Task 5: Make deferral fail closed and provenance truthful

**Files**
- Modify: `practical_agency/mission_os.py`
- Modify: `practical_agency/state_machine.py`
- Modify: `practical_agency/deferred_interest.py`
- Modify: `tests/test_mission_os.py`
- Modify: design/readme claim language where necessary

**Red tests**
- Paraphrased/overlapping proof work without clearance is refused.
- Ambiguous dependency is refused.
- Unrelated new frontier aim without basis is refused.
- Caller-supplied `created_at_revision` cannot forge provenance.

**Implementation**
- Require resolvable basis refs.
- Require explicit recorded critical-path clearance for deferrals not mechanically disjoint.
- Set `created_at_revision` during apply.
- Describe this as provenance/clearance enforcement, not semantic proof.

## Task 6: Journal world effects and persist receipt continuity

**Files**
- Modify: `practical_agency/filesystem_artifact.py`
- Modify: `practical_agency/state_machine.py`
- Modify: `practical_agency/validation.py`
- Modify: `contracts/mission-manifest.schema.json`
- Modify: `tests/test_filesystem_artifact.py`
- Modify: `tests/test_end_to_end_mission.py`

**Red tests**
- Request IDs containing path separators cannot escape the receipt directory.
- Failure before effect leaves a prepared/failed visible record and no artifact.
- Failure after atomic replacement cannot return success without committed/uncertain journal evidence.
- Checkpoint-only resume obtains the receipt ref from persisted state, verifies request/mission/revision/adapter identity, and recomputes artifact hash.
- Tampered or missing external receipts are refused.

**Implementation**
- Digest-based filenames.
- Atomic prepared → committed/uncertain journal transitions.
- Record external execution receipt in continuity through a revision-bound event.
- Add independent receipt verification helper.

## Task 7: Regression, independent review, and PR truthfulness

**Verification commands in CI**
- `python -m unittest discover -s tests -v`
- `python -m compileall -q practical_agency tests .github/scripts`
- `python .github/scripts/check_contracts.py`
- `python .github/scripts/check_package.py`
- `python .github/scripts/check_harness_surfaces.py`
- `python .github/scripts/check_public_content.py`
- wheel build/install smoke test
- DCO
- CodeQL/security checks available to the repository

**Review**
- Inspect the final diff against this design.
- Run the Superpowers requesting-code-review workflow.
- Address every substantive finding with the receiving-code-review workflow.

**Publication**
- Fast-forward `cursor/mission-os-design-a955` only after the hardening PR is fully green.
- Retitle and rewrite PR #7 to truthfully describe the cumulative integration and hardening surface.
- Post an evidence comment containing final commit, checks, changed boundaries, and any remaining operator-only steps.
- Close the temporary hardening PR after its commits are incorporated.
- Do not merge PR #7.
