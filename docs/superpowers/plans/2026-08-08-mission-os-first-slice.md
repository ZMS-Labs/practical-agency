# Mission OS First Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land internal mission-OS propose/apply, durable deferred interests, and a fixture receipted resume path that advances custody teeth without claiming field v1.

**Architecture:** Pure `mission_os` helpers emit typed proposals only. Steward/kernel applies them via a new `apply_mission_os` state-machine event that sole-writes `state.current_frontier` and `continuity.deferred_interests`. Coordinator remains the only dispatch driver; capability interrupts keep exact `ReturnPoint` (index + label). No second public skill; no PA skill-name router.

**Tech Stack:** Python 3.12 stdlib, `unittest`, existing `practical_agency` kernel, `FilesystemArtifactAdapter`, JSON Schema contracts.

**Spec:** `docs/superpowers/specs/2026-08-08-mission-os-and-manifest-v1-design.md` @ `ec7f95f` (operator-accepted 2026-08-08).

## Global Constraints

- Sole public skill remains `manifest`; do not add skills for resume/defer/mission-os.
- Stdlib-only deterministic core; no new required third-party deps.
- Every production behavior change: RED → GREEN → REFACTOR.
- Every commit: `Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>`.
- No skill-name inventory / stage→skill map in `practical_agency/` (extend existing ban test).
- `"helix it"` ≡ `"manifest this"` semantics only.
- Fixture e2e is **NOT CLAIMED** as RELEASE-1.0.0 world-power / field v1 / “proven useful.”
- Do not tag `0.1.0` or `1.0.0` in this plan.
- Public content must not expose private paths, credentials, or estate topology.
- Schema evolution: additive optional `continuity.deferred_interests` under still-`mission-manifest@1`, default `[]`.

---

## File structure

| File | Responsibility |
| --- | --- |
| `contracts/deferred-interest.schema.json` | Structural schema for `deferred-interest@1` |
| `contracts/mission-manifest.schema.json` | Add optional `continuity.deferred_interests` |
| `contracts/mission-event.schema.json` | Add `apply_mission_os` (+ absorb kinds if separate) |
| `practical_agency/deferred_interest.py` | Validate/normalize deferred-interest objects |
| `practical_agency/mission_os.py` | Pure propose helpers (no manifest mutation) |
| `practical_agency/validation.py` | Accept/validate `deferred_interests`; migrate default |
| `practical_agency/state_machine.py` | `apply_mission_os` (+ high absorb authority gate) |
| `practical_agency/checkpoint_store.py` | On load, default missing `deferred_interests` to `[]` before validate |
| `practical_agency/coordinator.py` | Emit-condition helper path; refuse inventing skill selection; return mismatch stays |
| `tests/helpers.py` | Include `deferred_interests: []` in minimal payload |
| `tests/test_deferred_interest.py` | Contract validation |
| `tests/test_mission_os.py` | Propose purity + constraint refusals |
| `tests/test_apply_mission_os.py` | Apply event + absorb gates |
| `tests/test_mission_os_slice.py` | End-to-end fixture slice (filesystem receipt + resume) |
| `docs/mission-manifest.md` | Document `deferred_interests` |
| `docs/release/MISSION-OS-SLICE-CLAIM-CEILING.md` | Explicit NOT CLAIMED boundaries |
| `tests/test_repository_contract.py` | Allow new contract file; claim-ceiling doc present |
| `tests/test_capability_discovery.py` | Ban inventory strings also cover `mission_os.py` path (already globs `*.py`) |

---

### Task 1: Deferred-interest schema + validator

**Files:**
- Create: `contracts/deferred-interest.schema.json`
- Modify: `contracts/mission-manifest.schema.json` (`continuity.properties`)
- Create: `practical_agency/deferred_interest.py`
- Modify: `practical_agency/validation.py`
- Modify: `tests/helpers.py`
- Modify: `tests/test_repository_contract.py` (required contract set)
- Create: `tests/test_deferred_interest.py`
- Modify: `examples/minimal-mission.json` if present without the field (migrate via validator default is enough for old fixtures; update helper)

**Interfaces:**
- Consumes: existing `validate_manifest_dict`
- Produces:
  - `validate_deferred_interest(obj: Mapping[str, Any], *, mission_id: str) -> list[str]`
  - `normalize_deferred_interests(value: object) -> list[dict[str, Any]]` (raises/returns errors via validation)
  - Schema property `continuity.deferred_interests` (array, default absent → treat as `[]`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deferred_interest.py
from __future__ import annotations

import unittest

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest
from practical_agency.validation import validate_manifest_dict
from tests.helpers import clone_payload


class DeferredInterestTests(unittest.TestCase):
    def test_high_requires_subject_refs(self) -> None:
        errors = validate_deferred_interest(
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "parked thread",
                "criticality": "high",
                "why_not_now": "not on critical path",
                "suggested_next": None,
                "subject_refs": [],
                "created_at_revision": 1,
                "status": "open",
            },
            mission_id="mission-001",
        )
        self.assertTrue(any("SUBJECT_REFS_REQUIRED" in e for e in errors))

    def test_manifest_accepts_deferred_interests_array(self) -> None:
        payload = clone_payload()
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "nice-to-have note",
                "criticality": "low",
                "why_not_now": "not required for completion proof",
                "suggested_next": None,
                "subject_refs": [],
                "created_at_revision": 1,
                "status": "open",
            }
        ]
        self.assertEqual(validate_manifest_dict(payload), [])
        MissionManifest.from_dict(payload)

    def test_unknown_continuity_field_still_rejected(self) -> None:
        payload = clone_payload()
        payload["continuity"]["not_a_real_field"] = []
        self.assertTrue(
            any(e.startswith("UNKNOWN_FIELD:") for e in validate_manifest_dict(payload))
        )


if __name__ == "__main__":
    unittest.main()
```

Also update `tests/test_repository_contract.py` required set to include `deferred-interest.schema.json`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_deferred_interest -v`

Expected: FAIL (import `practical_agency.deferred_interest` missing and/or UNKNOWN_FIELD on `deferred_interests`)

- [ ] **Step 3: Write minimal implementation**

`contracts/deferred-interest.schema.json` — closed object with fields from the design table (`schema` const `deferred-interest@1`, enums for `criticality`/`status`, etc.).

In `contracts/mission-manifest.schema.json` under `continuity.properties` add:

```json
"deferred_interests": {
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "mission_id",
      "summary",
      "criticality",
      "why_not_now",
      "suggested_next",
      "subject_refs",
      "created_at_revision",
      "status"
    ],
    "properties": {
      "schema": { "const": "deferred-interest@1" },
      "mission_id": { "type": "string", "minLength": 1 },
      "summary": { "type": "string", "minLength": 1 },
      "criticality": { "enum": ["low", "medium", "high"] },
      "why_not_now": { "type": "string", "minLength": 1 },
      "suggested_next": { "type": ["string", "null"] },
      "subject_refs": {
        "type": "array",
        "items": { "type": "string", "minLength": 1 }
      },
      "created_at_revision": { "type": "integer", "minimum": 1 },
      "status": { "enum": ["open", "absorbed", "discarded"] }
    }
  }
}
```

Do **not** add `deferred_interests` to `continuity.required` (additive optional).

`practical_agency/deferred_interest.py`:

```python
"""deferred-interest@1 validation helpers."""
from __future__ import annotations

from typing import Any, Mapping

_CRITICALITY = {"low", "medium", "high"}
_STATUS = {"open", "absorbed", "discarded"}
_REQUIRED = {
    "schema",
    "mission_id",
    "summary",
    "criticality",
    "why_not_now",
    "suggested_next",
    "subject_refs",
    "created_at_revision",
    "status",
}


def validate_deferred_interest(
    obj: Mapping[str, Any] | object, *, mission_id: str
) -> list[str]:
    if not isinstance(obj, Mapping):
        return ["DEFERRED_INTEREST_MUST_BE_OBJECT"]
    errors: list[str] = []
    if set(obj) - _REQUIRED:
        errors.append("DEFERRED_INTEREST_UNKNOWN_FIELD")
    if obj.get("schema") != "deferred-interest@1":
        errors.append("DEFERRED_INTEREST_SCHEMA")
    if obj.get("mission_id") != mission_id:
        errors.append("DEFERRED_INTEREST_MISSION_MISMATCH")
    if obj.get("criticality") not in _CRITICALITY:
        errors.append("DEFERRED_INTEREST_CRITICALITY")
    if obj.get("status") not in _STATUS:
        errors.append("DEFERRED_INTEREST_STATUS")
    refs = obj.get("subject_refs")
    if not isinstance(refs, list) or any(
        not isinstance(x, str) or not x.strip() for x in refs
    ):
        errors.append("DEFERRED_INTEREST_SUBJECT_REFS")
    elif obj.get("criticality") == "high" and not refs:
        errors.append("SUBJECT_REFS_REQUIRED_FOR_HIGH")
    # nonempty summary/why_not_now; suggested_next null|str; created_at_revision int>=1
    return errors
```

Update `validation.py`:
- Add `"deferred_interests"` to `ALLOWED` continuity keys and `LIST_FIELDS["continuity"]`.
- Before unknown-key checks, if `deferred_interests` missing, treat as present empty list for validation of new manifests **or** require helpers to always include it; prefer: if key absent, do not error; if present, validate each item via `validate_deferred_interest`.
- Keep `additionalProperties` false semantics via ALLOWED set.

Update `tests/helpers.py` `minimal_payload()` continuity to include `"deferred_interests": []`.

Update `tests/test_repository_contract.py` required filenames set.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_deferred_interest tests.test_manifest_model -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contracts/deferred-interest.schema.json contracts/mission-manifest.schema.json \
  practical_agency/deferred_interest.py practical_agency/validation.py \
  tests/helpers.py tests/test_deferred_interest.py tests/test_repository_contract.py \
  examples/minimal-mission.json
git commit -m "feat: additive deferred-interest@1 on mission-manifest continuity

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

### Task 2: Mission OS propose helpers (pure)

**Files:**
- Create: `practical_agency/mission_os.py`
- Create: `tests/test_mission_os.py`

**Interfaces:**
- Consumes: `MissionManifest`, `validate_deferred_interest`
- Produces:
  - `@dataclass frozen MissionOsProposal` with `kind: str` and `payload: dict[str, Any]`
  - `propose_frontier_patch(manifest, labels: list[str]) -> MissionOsProposal`
  - `propose_replan_slice(manifest, *, new_frontier: list[str], contradiction_refs: list[str]) -> MissionOsProposal`
  - `propose_defer(manifest, interest: Mapping[str, Any], *, completion_proof_ids: Sequence[str] | None = None) -> MissionOsProposal`
  - `propose_return_rebind(manifest, invalidate: list[Mapping[str, Any]]) -> MissionOsProposal`
  - `emit_unanswered_condition(manifest, condition: str, frontier_index: int = 0) -> dict` with keys `condition`, `return_point` only (no skill id)
  - All propose_* **copy** inputs; never mutate `manifest`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mission_os.py
from __future__ import annotations

import unittest

from practical_agency.mission_os import (
    emit_unanswered_condition,
    propose_defer,
    propose_frontier_patch,
    propose_replan_slice,
)
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


class MissionOsProposeTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = [
            "write authorized artifact",
            "verify artifact hash",
        ]
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        return MissionManifest.from_dict(payload)

    def test_propose_does_not_mutate_manifest(self) -> None:
        manifest = self.active()
        before = manifest.to_dict()
        proposal = propose_frontier_patch(
            manifest, ["write authorized artifact", "verify artifact hash"]
        )
        self.assertEqual(proposal.kind, "frontier_patch")
        self.assertEqual(manifest.to_dict(), before)
        self.assertEqual(
            manifest.state["current_frontier"],
            ["write authorized artifact", "verify artifact hash"],
        )

    def test_frontier_labels_reject_skill_name_shaped_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "FRONTIER_LABEL_FORBIDDEN"):
            propose_frontier_patch(self.active(), ["run metacognate next"])

    def test_defer_refuses_completion_proof_necessary_summary(self) -> None:
        manifest = self.active()
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "artifact:validator-pass",
            "criticality": "low",
            "why_not_now": "distraction",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": 2,
            "status": "open",
        }
        with self.assertRaisesRegex(ValueError, "DEFER_CRITICAL_PATH"):
            propose_defer(manifest, interest)

    def test_emit_condition_has_no_capability_id(self) -> None:
        out = emit_unanswered_condition(
            self.active(), "approach uncertain for this claim", frontier_index=0
        )
        self.assertEqual(
            set(out),
            {"condition", "return_point"},
        )
        self.assertNotIn("capability_id", out)
        self.assertEqual(out["return_point"]["frontier_index"], 0)

    def test_replan_requires_contradiction_refs(self) -> None:
        with self.assertRaisesRegex(ValueError, "REPLAN_CONTRADICTION_REQUIRED"):
            propose_replan_slice(
                self.active(),
                new_frontier=["repair live drift"],
                contradiction_refs=[],
            )


if __name__ == "__main__":
    unittest.main()
```

Forbidden label rule (deterministic, narrow): casefold label may not equal or contain as a whole-token any of a small **banned token set used only for anti-inventory tests** — wait: putting skill names in mission_os.py would fail `test_production_code_contains_no_known_member_inventory`.

**Critical constraint:** `mission_os.py` must NOT contain the strings `gauntlet`, `metacognate`, or `write-goal`.

Implement label ban without naming those skills: reject labels matching regex `(?i)\b(skill|invoke|run)\s+[a-z0-9_-]+\b` or reject if label equals a caller-supplied forbidden set defaulting to empty, and in tests pass forbidden tokens only inside the test file:

```python
propose_frontier_patch(manifest, labels, forbidden_substrings=("metacognate",))
```

Default production call uses `forbidden_substrings=()` plus structural rule: labels must not contain `://skill` or prefix `skill:`. Spec says “never skill names” — enforce via:

1. Labels must be non-empty strings without newlines.
2. Labels must not start with `skill:` or `capability:`.
3. Optional `forbidden_substrings` parameter for callers/tests.

Do **not** hardcode epistemic skill names in `practical_agency/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mission_os -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# practical_agency/mission_os.py (sketch)
@dataclass(frozen=True, slots=True)
class MissionOsProposal:
    kind: str
    payload: dict[str, Any]

def propose_frontier_patch(manifest, labels, *, forbidden_substrings=()) -> MissionOsProposal:
    _validate_labels(labels, forbidden_substrings=forbidden_substrings)
    return MissionOsProposal("frontier_patch", {"labels": list(labels)})

def propose_replan_slice(manifest, *, new_frontier, contradiction_refs, forbidden_substrings=()) -> MissionOsProposal:
    if not contradiction_refs:
        raise ValueError("REPLAN_CONTRADICTION_REQUIRED")
    _validate_labels(new_frontier, forbidden_substrings=forbidden_substrings)
    return MissionOsProposal(
        "replan_slice",
        {"labels": list(new_frontier), "contradiction_refs": list(contradiction_refs)},
    )

def propose_defer(manifest, interest, ...) -> MissionOsProposal:
    # validate interest; if summary or subject_refs intersect unmet completion_proof / scope_proof tokens → DEFER_CRITICAL_PATH
    # if sole frontier item would be removed by deferring that label → DEFER_CRITICAL_PATH
    ...

def emit_unanswered_condition(manifest, condition, frontier_index=0) -> dict:
    from practical_agency.coordinator import ReturnPoint  # or duplicate small dict build to avoid cycles
    ...
```

Avoid import cycles: build return_point dict locally from manifest fields (same shape as `ReturnPoint.to_dict()`).

Defer critical-path heuristic (deterministic for v1 slice):
- If `interest["summary"]` equals any unmet proof id in `outcome.completion_proof` or `outcome.scope_proof` not yet in `continuity.durable_artifacts`, raise `DEFER_CRITICAL_PATH`.
- If `interest["summary"]` equals the only item in `state.current_frontier`, raise `DEFER_CRITICAL_PATH`.
- Otherwise allow.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_mission_os tests.test_capability_discovery.CapabilityDiscoveryTests.test_production_code_contains_no_known_member_inventory -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add practical_agency/mission_os.py tests/test_mission_os.py
git commit -m "feat: pure mission-os proposal helpers

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

### Task 3: `apply_mission_os` state transition

**Files:**
- Modify: `contracts/mission-event.schema.json` (add kind `apply_mission_os`)
- Modify: `practical_agency/state_machine.py`
- Create: `tests/test_apply_mission_os.py`
- Modify: any event-kind exhaustiveness tests if present

**Interfaces:**
- Consumes: `MissionOsProposal` payload via `MissionEvent(kind="apply_mission_os", ...)`
- Produces: updated `MissionManifest` with bumped revision; records `continuity.decisions` entry `{kind: "mission-os-apply", proposal_kind, actor_ref, ...}`

Event data shapes:

```python
# frontier_patch / replan_slice
{"proposal_kind": "frontier_patch", "labels": [...], "contradiction_refs": [...]  # required for replan_slice}

# defer
{"proposal_kind": "defer", "interest": {deferred-interest@1...}}

# return_rebind
{"proposal_kind": "return_rebind", "invalidate": [ReturnPoint dicts]}

# absorb (medium/low)
{"proposal_kind": "absorb", "interest_index": 0}  # or interest id/summary match

# absorb high — must include operator absorb marker
{"proposal_kind": "absorb", "interest_index": 0, "operator_absorb": True}
# and actor_ref must be operator; amendments must grow OR operator_absorb + explicit amendment text in data["amendment"]
```

Rules inside `apply_event`:
1. Allowed from `active` (and `blocked` only for replan_slice that addresses reconciliation — keep v1 simpler: **active only**).
2. Actor may be `mission-steward` for frontier/replan/defer/return_rebind/low-medium absorb.
3. Never modify `authority.instruction` or `outcome.desired_state`.
4. `frontier_patch`/`replan_slice`: set `state.current_frontier = labels`; set `next_action = labels[0] if labels else None`; for replan require nonempty `contradiction_refs` and append them into `truth.contradictions` if not present (as strings or `{subject_ref, note}` — use string refs for slice simplicity).
5. `defer`: append interest to `continuity.deferred_interests` (ensure key exists); **do not** remove critical frontier items; refuse if validate_deferred_interest errors or critical-path heuristic fails (duplicate propose checks).
6. `absorb`: locate open interest; if `criticality == "high"`, require `_operator_only` and either new `authority.amendments` entry in this event (`amendment` field) or fail `HIGH_ABSORB_AMENDMENT_REQUIRED`; set status `absorbed`; do **not** auto-insert frontier labels from `suggested_next`.
7. `return_rebind`: append decision listing invalidated return points (no frontier change).
8. Always append `mission-os-apply` decision.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_mission_os.py
from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from tests.helpers import clone_payload


class ApplyMissionOsTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["write authorized artifact"]
        payload["state"]["next_action"] = "write authorized artifact"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = []
        return MissionManifest.from_dict(payload)

    def test_apply_frontier_patch_writes_sole_carrier(self) -> None:
        updated = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact", "verify receipt"],
                },
            ),
        )
        self.assertEqual(
            updated.state["current_frontier"],
            ["write authorized artifact", "verify receipt"],
        )
        self.assertEqual(updated.state["next_action"], "write authorized artifact")
        self.assertEqual(updated.revision, 3)
        kinds = [d.get("kind") for d in updated.continuity["decisions"]]
        self.assertIn("mission-os-apply", kinds)

    def test_apply_does_not_change_instruction_or_desired_state(self) -> None:
        manifest = self.active()
        updated = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact"],
                },
            ),
        )
        self.assertEqual(
            updated.authority["instruction"], manifest.authority["instruction"]
        )
        self.assertEqual(
            updated.outcome["desired_state"], manifest.outcome["desired_state"]
        )

    def test_defer_persists_interest(self) -> None:
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "explore alternate doc layout",
            "criticality": "low",
            "why_not_now": "not required for completion proof",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": 2,
            "status": "open",
        }
        updated = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {"proposal_kind": "defer", "interest": interest},
            ),
        )
        self.assertEqual(len(updated.continuity["deferred_interests"]), 1)
        self.assertEqual(
            updated.state["current_frontier"], ["write authorized artifact"]
        )

    def test_high_absorb_without_amendment_refused(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "touch protected area later",
                "criticality": "high",
                "why_not_now": "not now",
                "suggested_next": "rewrite unrelated files",
                "subject_refs": ["repo:example@rev-1"],
                "created_at_revision": 2,
                "status": "open",
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(TransitionError, "HIGH_ABSORB_AMENDMENT_REQUIRED"):
            apply_event(
                manifest,
                MissionEvent(
                    "apply_mission_os",
                    "operator:test",
                    {"proposal_kind": "absorb", "interest_index": 0},
                ),
            )

    def test_high_absorb_with_amendment_marks_absorbed_without_frontier_smuggle(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["write authorized artifact"]
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "touch protected area later",
                "criticality": "high",
                "why_not_now": "not now",
                "suggested_next": "rewrite unrelated files",
                "subject_refs": ["repo:example@rev-1"],
                "created_at_revision": 2,
                "status": "open",
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        updated = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "operator:test",
                {
                    "proposal_kind": "absorb",
                    "interest_index": 0,
                    "amendment": "Operator approves absorbing high deferred interest for later scheduling only.",
                },
            ),
        )
        self.assertEqual(updated.continuity["deferred_interests"][0]["status"], "absorbed")
        self.assertEqual(updated.state["current_frontier"], ["write authorized artifact"])
        self.assertNotIn(
            "rewrite unrelated files", updated.state["current_frontier"]
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_apply_mission_os -v`

Expected: FAIL `UNKNOWN_EVENT:apply_mission_os`

- [ ] **Step 3: Write minimal implementation**

Add `"apply_mission_os"` to `_ALLOWED_FROM` with `{MissionStatus.ACTIVE.value}` and implement the branch in `apply_event` as specified. Update `mission-event.schema.json` enum.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_apply_mission_os tests.test_state_machine -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contracts/mission-event.schema.json practical_agency/state_machine.py tests/test_apply_mission_os.py
git commit -m "feat: apply_mission_os transition for OS proposals

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

### Task 4: Checkpoint migrate + return-point / unapplied gates

**Files:**
- Modify: `practical_agency/checkpoint_store.py` (`load` path)
- Modify: `practical_agency/coordinator.py`
- Modify: `tests/test_checkpoint_store.py` (or new cases)
- Modify: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: manifests missing `deferred_interests`
- Produces:
  - `FileCheckpointStore.load` injects `continuity.deferred_interests = []` when absent before `MissionManifest.from_dict`
  - `coordinate_once(..., require_mission_os_apply: bool = False)` OR simpler rule:

**Dispatch gate (slice rule):**  
If `execution_request` is present and the caller passes `require_applied_frontier=True`, require that a frontier/replan was **applied** earlier on this mission. Defer (and other non-frontier applies) bump revision and must **not** invalidate that custody.

Deterministic rule (amended after first-slice integration — design path is frontier apply → optional defer → dispatch):

```python
def _frontier_apply_present(manifest) -> bool:
    rev = manifest.revision
    latest: int | None = None
    for item in manifest.continuity.get("decisions", []):
        if not isinstance(item, Mapping) or item.get("kind") != "mission-os-apply":
            continue
        if item.get("proposal_kind") not in {"frontier_patch", "replan_slice"}:
            continue
        at_revision = item.get("at_revision")
        if isinstance(at_revision, int) and (latest is None or at_revision > latest):
            latest = at_revision
    return latest is not None and latest <= rev
```

When `coordinate_once(..., require_applied_frontier=True)` and execution_request set, BLOCK with `MISSION_OS_APPLY_REQUIRED` unless `_frontier_apply_present`.

Default `require_applied_frontier=False` to avoid breaking existing tests; mission-os slice and new tests set True.

Also cover: frontier apply then defer still allows dispatch when `require_applied_frontier=True`.

Return-point: add test that after `apply_mission_os` replan changes label at index 0, `apply_capability_result` with old return_point raises `RETURN_POINT_MISMATCH`.

- [ ] **Step 1: Write failing tests**

```python
def test_old_checkpoint_without_deferred_interests_loads(self):
    # save bytes lacking deferred_interests by temporarily writing raw JSON if needed,
    # or construct pre-field payload through store after stripping key post-serialize hook.
    ...

def test_dispatch_blocked_without_applied_frontier_when_required(self):
    decision = coordinate_once(
        active,
        execution_request={...},
        checkpoint_store=store,
        require_applied_frontier=True,
    )
    self.assertEqual(decision.kind, "BLOCK")
    self.assertIn("MISSION_OS_APPLY_REQUIRED", decision.reason)

def test_stale_return_point_after_replan_mismatches(self):
    # REQUEST_CAPABILITY with return at index 0 label A
    # apply replan changing label
    # apply_capability_result with old returned_control_point → CoordinationError RETURN_POINT_MISMATCH
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m unittest tests.test_coordinator tests.test_checkpoint_store -v` (targeted new tests)

- [ ] **Step 3: Implement migrate + flags**

In `apply_mission_os` decision dict include `"at_revision": data["revision"]` **after** revision bump (store the new revision).

In `checkpoint_store.load`, after reading JSON dict and before `MissionManifest.from_dict`:

```python
continuity = payload.setdefault("continuity", {})
continuity.setdefault("deferred_interests", [])
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: PASS (full suite)

- [ ] **Step 5: Commit**

```bash
git add practical_agency/checkpoint_store.py practical_agency/coordinator.py \
  practical_agency/state_machine.py tests/test_coordinator.py tests/test_checkpoint_store.py
git commit -m "feat: migrate deferred_interests; gate OS-bound dispatch

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

### Task 5: Fixture mission-OS slice (filesystem receipt + resume)

**Files:**
- Create: `tests/test_mission_os_slice.py`
- Create: `docs/release/MISSION-OS-SLICE-CLAIM-CEILING.md`
- Modify: `docs/mission-manifest.md` (document deferred_interests)
- Modify: `tests/test_repository_contract.py` (require claim-ceiling doc)

**Interfaces:**
- Consumes: Tasks 1–4 + `FilesystemArtifactAdapter`
- Produces: one unittest proving the design’s first slice path; docs stating NOT CLAIMED for field v1

- [ ] **Step 1: Write failing test**

```python
# tests/test_mission_os_slice.py
"""Fixture path for mission OS first slice — NOT field v1."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import FilesystemArtifactAdapter
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import propose_defer, propose_frontier_patch
from practical_agency.state_machine import MissionEvent, apply_event
from tests.helpers import clone_payload


class MissionOsSliceTests(unittest.TestCase):
    def test_propose_apply_defer_filesystem_resume_independent_accept(self) -> None:
        original = "Manifest authorized text artifact under mission OS custody."
        payload = clone_payload()
        payload["authority"]["instruction"] = original
        payload["authority"]["acceptable_costs"] = [
            "one feature branch",
            "one local artifact write",
        ]
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["outcome"]["completion_proof"] = ["artifact:validator-pass"]
        draft = MissionManifest.from_dict(payload)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root / "checkpoints")
            world = root / "world"
            receipt0 = store.save(draft)
            active = apply_event(
                draft,
                MissionEvent("approve", "operator:test", {"checkpoint_ref": receipt0.path}),
            )

            proposal = propose_frontier_patch(
                active,
                ["write authorized artifact", "observe receipt"],
            )
            active = apply_event(
                active,
                MissionEvent(
                    "apply_mission_os",
                    "mission-steward",
                    {"proposal_kind": proposal.kind, **proposal.payload},
                ),
            )

            defer_prop = propose_defer(
                active,
                {
                    "schema": "deferred-interest@1",
                    "mission_id": "mission-001",
                    "summary": "optional docs polish",
                    "criticality": "low",
                    "why_not_now": "not required for completion proof",
                    "suggested_next": None,
                    "subject_refs": [],
                    "created_at_revision": active.revision,
                    "status": "open",
                },
            )
            active = apply_event(
                active,
                MissionEvent(
                    "apply_mission_os",
                    "mission-steward",
                    {"proposal_kind": defer_prop.kind, **defer_prop.payload},
                ),
            )
            self.assertEqual(len(active.continuity["deferred_interests"]), 1)
            self.assertEqual(
                active.state["current_frontier"][0], "write authorized artifact"
            )

            adapter = FilesystemArtifactAdapter(world)
            decision = coordinate_once(
                active,
                execution_request={
                    "capability_id": "filesystem-artifact",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": [
                        "relpath:mission-artifacts/os-slice.txt",
                        "utf8:os-slice-body",
                    ],
                    "estimated_costs": ["one local artifact write"],
                    "action": "write-text",
                },
                checkpoint_store=store,
                require_applied_frontier=True,
            )
            self.assertEqual(decision.kind, "DISPATCH")
            result = dispatch_once(active, decision, adapter)
            self.assertEqual(result["status"], "completed")

            acted = apply_event(
                active,
                MissionEvent(
                    "record_action",
                    "mission-steward",
                    {"action_ref": result["artifact_refs"][0]},
                ),
            )
            observed = apply_event(
                acted,
                MissionEvent(
                    "record_observation",
                    "observer:test",
                    {
                        "artifact_ref": "artifact:validator-pass",
                        "fact": {
                            "subject_ref": "artifact:os-slice",
                            "value": "os-slice-body",
                        },
                    },
                ),
            )
            ckpt = store.save(observed)

            del draft, active, acted, observed, decision, result
            resumed = store.load(ckpt)
            self.assertEqual(resumed.authority["instruction"], original)
            self.assertEqual(len(resumed.continuity["deferred_interests"]), 1)
            self.assertTrue(
                (world / "mission-artifacts" / "os-slice.txt").is_file()
            )

            verifying = apply_event(
                resumed, MissionEvent("begin_verification", "mission-steward", {})
            )
            with self.assertRaisesRegex(Exception, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
                apply_event(
                    verifying,
                    MissionEvent(
                        "accept",
                        "mission-steward",
                        {
                            "verdict": "PASS",
                            "evidence_refs": ["artifact:validator-pass"],
                            "coverage_limits": ["fixture slice"],
                        },
                    ),
                )
            completed = apply_event(
                verifying,
                MissionEvent(
                    "accept",
                    "reviewer:test",
                    {
                        "verdict": "PASS",
                        "evidence_refs": ["artifact:validator-pass"],
                        "coverage_limits": [
                            "fixture slice only — NOT field v1 / RELEASE-1.0.0"
                        ],
                    },
                ),
            )
            self.assertEqual(completed.state["status"], "completed")
```

Adjust `begin_verification` / proof readiness to match existing kernel rules (`_missing_proof_refs`) — copy patterns from `tests/test_end_to_end_mission.py` if proof bundle needs durable artifact names aligned.

- [ ] **Step 2: Run to verify fail**

Run: `python -m unittest tests.test_mission_os_slice -v`

Expected: FAIL until Task 4 flag and apply path exist (or FAIL on proof readiness — fix test to match kernel)

- [ ] **Step 3: Implement docs + fix test against real proof rules**

Write `docs/release/MISSION-OS-SLICE-CLAIM-CEILING.md`:

```markdown
# Mission OS first-slice claim ceiling

Status: **fixture / custody machinery only**

This slice does **NOT** claim:
- `1.0.0` / field v1 readiness
- RELEASE-1.0.0 world-power beyond the existing bounded filesystem adapter path
- live harness fire for all supported harnesses
- comparative efficacy or “proven useful”
- that a fixture e2e is an external durable field mission

It **does** claim: deterministic propose→apply→defer→receipted write→resume→independent accept works under unittest fixtures on the implementing tip.
```

Update `docs/mission-manifest.md` continuity row to mention `deferred_interests`.

- [ ] **Step 4: Full verification**

Run:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_mission_os_slice.py docs/release/MISSION-OS-SLICE-CLAIM-CEILING.md \
  docs/mission-manifest.md tests/test_repository_contract.py
git commit -m "test: mission-os fixture slice with explicit claim ceiling

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

### Task 6: Design status + helix oracle note + inventory guardrail

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-mission-os-and-manifest-v1-design.md` (status → operator-accepted; epistemic record)
- Modify: `tests/test_coordinator.py` (assert carry/helix/manifest equivalence already present — add `carry this through` if missing)
- Modify: `tests/test_mission_os.py` — assert `mission_os.py` source has no `skills/` directory creation and no stage map dict literal patterns if cheap

- [ ] **Step 1: Update design status block**

Set:

```markdown
**Status:** operator-accepted 2026-08-08 (amended tip `ec7f95f`; implementation plan `docs/superpowers/plans/2026-08-08-mission-os-first-slice.md`)
```

Update epistemic record table: operator accept = yes (chat 2026-08-08).

- [ ] **Step 2: Run full suite**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-08-mission-os-and-manifest-v1-design.md tests/test_coordinator.py
git commit -m "docs: record operator accept; bind mission-os implementation plan

Signed-off-by: SternOne <89846440+SternOne@users.noreply.github.com>"
```

---

## Self-review (writing-plans)

| Spec requirement | Task |
| --- | --- |
| Additive `deferred_interests` under `@1` | Task 1 |
| Pure OS propose; sole writer via apply | Tasks 2–3 |
| Re-plan no ends / labels not skill names | Tasks 2–3 |
| Defer critical-path refuse | Tasks 2–3 |
| High absorb amendment | Task 3 |
| ReturnPoint index + stale mismatch | Task 4 |
| Unapplied proposal cannot justify dispatch | Task 4 (`require_applied_frontier`) |
| Condition emit without skill selection | Task 2 |
| Fixture slice + NOT CLAIMED | Task 5 |
| helix synonym oracle | Task 6 (existing + carry) |
| No inventory in production | Tasks 2/6 + existing discovery test |
| Independent accept / no self-cert | Task 5 |

Placeholder scan: none intentionally left; implementers must align `begin_verification` proof bundle with existing `_missing_proof_refs` behavior when wiring Task 5.

Type consistency: `MissionOsProposal.kind` values are `frontier_patch|replan_slice|defer|return_rebind`; apply event uses `proposal_kind` with the same strings; absorb is apply-only (`proposal_kind: absorb`).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-08-mission-os-first-slice.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with executing-plans checkpoints  

Which approach?
