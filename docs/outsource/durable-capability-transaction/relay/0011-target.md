schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: ede617fadcb1de348a7e6f5b9904f2eca3069224
status: PARTIAL
summary: |
  Stage 5 production-only patch for fail-closed orphaned capability execution. The begin transition now persists the mission event ID as the execution-attempt identity and the controller process-instance ID as the execution owner. Pathless engagement detects differently owned in-progress executions before receipt, drift, or target inspection; durably transitions them to unknown; blocks the mission with CAPABILITY_EFFECT_UNKNOWN:<grant_id> in both blocker collections; and returns the recovery checkpoint without replay. Existing unknown markers also short-circuit later engagements. Canonical capability issuance and execution refuse with the exact durable marker until a future external-receipt reconciliation transition exists, and generic unblocking cannot remove the marker. The used grant and null result are preserved, and no capability result, effect, result artifact, or result decision is synthesized. Tests were not run.
work_product: |
  diff --git a/practical_agency/controller.py b/practical_agency/controller.py
  --- a/practical_agency/controller.py
  +++ b/practical_agency/controller.py
  @@ -326,6 +326,13 @@ def _status_summary(manifest: MissionManifest) -> dict[str, Any]:
           "next_action": manifest.state["next_action"],
           "unresolved_verdicts": list(manifest.integrity["unresolved_verdicts"]),
       }
  
  
  +def _capability_effect_unknown_marker(manifest: MissionManifest) -> str | None:
  +    for marker in manifest.integrity["unresolved_verdicts"]:
  +        if marker.startswith("CAPABILITY_EFFECT_UNKNOWN:"):
  +            return marker
  +    return None
  +
  +
   class ManifestController:
       """Compose pathless mission operations without exposing storage identity."""
  
  @@ -405,3 +412,32 @@
           manifest = discovered.manifest
           store = self._store(binding.workspace_root, manifest.mission_id)
  +        recovery_checkpoint = None
  +        for record in manifest.capabilities.get("invoked", []):
  +            if (
  +                not isinstance(record, Mapping)
  +                or record.get("execution_state") != "in_progress"
  +                or record.get("execution_owner_id") == self.process_instance_id
  +            ):
  +                continue
  +            try:
  +                manifest = apply_event_data(
  +                    manifest,
  +                    "mark_capability_execution_unknown",
  +                    "mission-steward:capability",
  +                    {"grant_id": record.get("grant_id")},
  +                )
  +            except TransitionError as error:
  +                raise ControllerError(str(error)) from error
  +            recovery_checkpoint = store.save(manifest)
  +        unknown_marker = _capability_effect_unknown_marker(manifest)
  +        if unknown_marker is not None:
  +            checkpoint = recovery_checkpoint or discovered.receipt
  +            return {
  +                "status": "engaged",
  +                **_status_summary(manifest),
  +                "checkpoint_ref": checkpoint.path,
  +                "checkpoint_sha256": checkpoint.sha256,
  +                "drift_findings": [],
  +                "process_instance_id": self.process_instance_id,
  +            }
           try:
               definition = _durable_definition(manifest)
  @@ -581,2 +617,5 @@
           discovered = self._discover(binding.workspace_root)
  +        unknown_marker = _capability_effect_unknown_marker(discovered.manifest)
  +        if unknown_marker is not None:
  +            raise ControllerError(unknown_marker)
           descriptor = self._descriptor(capability_id)
  @@ -727,3 +766,6 @@
           discovered = self._discover(binding.workspace_root)
           manifest = discovered.manifest
  +        unknown_marker = _capability_effect_unknown_marker(manifest)
  +        if unknown_marker is not None:
  +            raise ControllerError(unknown_marker)
           records = [
  @@ -829,4 +871,5 @@
                       "operation": operation,
                       "target": target,
                       "evidence_refs": refs,
  +                    "execution_owner_id": self.process_instance_id,
                   },
  diff --git a/practical_agency/state_machine.py b/practical_agency/state_machine.py
  --- a/practical_agency/state_machine.py
  +++ b/practical_agency/state_machine.py
  @@ -139,5 +139,9 @@
       "begin_capability_execution": {
           MissionStatus.ACTIVE.value,
           MissionStatus.BLOCKED.value,
       },
  +    "mark_capability_execution_unknown": {
  +        MissionStatus.ACTIVE.value,
  +        MissionStatus.BLOCKED.value,
  +    },
       "record_capability_result": {MissionStatus.ACTIVE.value, MissionStatus.BLOCKED.value},
  @@ -513,5 +517,11 @@
           reconciliation_blockers = [
               item
               for item in state["blockers"]
  -            if _reconciliation_subject(item) is not None
  +            if (
  +                _reconciliation_subject(item) is not None
  +                or (
  +                    isinstance(item, str)
  +                    and item.startswith("CAPABILITY_EFFECT_UNKNOWN:")
  +                )
  +            )
           ]
  @@ -684,6 +694,7 @@
           if set(payload) != {
               "grant_id",
               "operation",
               "target",
               "evidence_refs",
  +            "execution_owner_id",
           }:
  @@ -691,5 +702,6 @@
           grant_id = payload.get("grant_id")
           operation = payload.get("operation")
           target = payload.get("target")
           evidence_refs = payload.get("evidence_refs")
  +        execution_owner_id = payload.get("execution_owner_id")
           if (
  @@ -700,3 +712,5 @@
               or not isinstance(target, str)
               or not target.strip()
  +            or not isinstance(execution_owner_id, str)
  +            or not execution_owner_id.strip()
               or not isinstance(evidence_refs, list)
  @@ -744,3 +758,5 @@
           except CapabilityGrantError as error:
               raise TransitionError(str(error)) from error
  +        record["execution_attempt_id"] = event.event_id
  +        record["execution_owner_id"] = execution_owner_id
           record["execution_state"] = "in_progress"
  @@ -752,6 +768,34 @@
                   "operation": operation,
                   "target": target,
               }
           )
  
  +    elif event.kind == "mark_capability_execution_unknown":
  +        if set(payload) != {"grant_id"}:
  +            raise TransitionError("CAPABILITY_UNKNOWN_EVENT_INVALID")
  +        grant_id = payload.get("grant_id")
  +        if not isinstance(grant_id, str) or not grant_id.strip():
  +            raise TransitionError("CAPABILITY_GRANT_ID_REQUIRED")
  +        invoked = [
  +            item
  +            for item in data["capabilities"].get("invoked", [])
  +            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
  +        ]
  +        if len(invoked) != 1:
  +            raise TransitionError("CAPABILITY_GRANT_NOT_FOUND")
  +        record = invoked[0]
  +        if record.get("execution_state") != "in_progress":
  +            raise TransitionError("CAPABILITY_GRANT_NOT_IN_PROGRESS")
  +        if record.get("result") is not None:
  +            raise TransitionError("CAPABILITY_RESULT_REPLAY")
  +        grant = record.get("grant")
  +        if not isinstance(grant, Mapping) or grant.get("used") is not True:
  +            raise TransitionError("CAPABILITY_EXECUTION_STATE_INVALID")
  +        marker = f"CAPABILITY_EFFECT_UNKNOWN:{grant_id}"
  +        record["execution_state"] = "unknown"
  +        _append_unique(state["blockers"], marker)
  +        _append_unique(integrity["unresolved_verdicts"], marker)
  +        state["status"] = MissionStatus.BLOCKED.value
  +        state["next_action"] = f"external receipt required for {grant_id}"
  +
       elif event.kind == "record_capability_result":
evidence: |
  REQUIREMENT-TO-HUNK MAP

  1. Durable execution-attempt and owner identity
     - controller.py, begin_capability_execution payload hunk: binds execution_owner_id to the executing controller's process_instance_id before the begun checkpoint is saved.
     - state_machine.py, begin transition hunks: validates the owner, stores event.event_id as execution_attempt_id, stores execution_owner_id, consumes the durable grant, and only then records execution_state=in_progress.
     - The existing controller ordering still saves this begun manifest before execute_read, so both forced-exit cases leave the same durable authority state: used=true, in_progress, result=null, with explicit attempt and owner identity.

  2. Replacement-process orphan detection without observation
     - controller.py, manifest_engage recovery hunk: compares each in-progress record's durable execution_owner_id to the replacement controller's process_instance_id before durable-definition lookup, filesystem-receipt inspection, governed-workspace drift inspection, or any capability target operation.
     - A missing legacy owner is conservatively different from the replacement owner and is therefore classified unknown rather than replayed or inferred complete.
     - Each recovery transition is checkpointed immediately through the existing real FileCheckpointStore.

  3. Honest unknown classification and blocked durable state
     - state_machine.py, mark_capability_execution_unknown hunk: accepts only one existing in-progress record whose result remains null and whose grant is already used; changes only execution_state to unknown; adds CAPABILITY_EFFECT_UNKNOWN:<grant_id> to state.blockers and integrity.unresolved_verdicts; and sets mission status to blocked.
     - The transition does not set result, append capability-result:<grant_id>, append a capability-result decision, or assert any observed effect. Zero effect and completed-but-unrecorded effect therefore receive the same unknown classification.

  4. Pathless recovery checkpoint and replay-free engagement
     - controller.py, manifest_engage recovery hunk: returns the newly saved checkpoint and blocked status immediately after classification.
     - Existing CAPABILITY_EFFECT_UNKNOWN markers also short-circuit subsequent engagements before receipt, drift, or target inspection, preventing engagement itself from becoming an accidental re-observation route.

  5. Original retry and replacement issue/execute refusal
     - controller.py, unknown-marker helper plus manifest_capability_issue and manifest_capability_execute guard hunks: return the exact durable CAPABILITY_EFFECT_UNKNOWN:<grant_id> refusal before descriptor resolution, grant execution, or target observation.
     - The global mission-level guard is a conservative superset of refusing another grant for the unresolved return point: no canonical capability transaction can proceed while any capability effect remains unknown.

  6. Remain blocked pending a future external-receipt contract
     - state_machine.py, unblock hunk: treats CAPABILITY_EFFECT_UNKNOWN markers as reconciliation-protected blockers. Generic unblock cannot remove one by naming it or by clearing all blockers.
     - No reconciliation transition is introduced, so resolution remains unavailable until a separately authorized external-receipt contract is designed.

  7. Preservation of the 13 focused controls
     - Normal pending-to-in_progress-to-consumed execution is unchanged except for additive attempt/owner metadata.
     - All new controller refusals are gated by a marker that does not exist on the 13 pre-existing paths.
     - No test, MCP schema, capability-discovery, web, proof-integration, principal-independence, grant-shape, request-shape, result-shape, or filesystem-operation code is changed.
     - No manifest schema or validation weakening is required: capability invocation records are already open objects, execution_state is not schema-enumerated, and blocked status plus nonempty marker strings satisfy the existing validation model.

  EXPECTED COMMITTED-STAGE-4 EFFECTS — NOT EXECUTED HERE

  - Before-read forced exit: engagement creates a newer checkpoint, preserves zero journal reads, marks the original transaction unknown, and blocks replacement activity.
  - After-one-read forced exit: engagement creates the same unknown/blocked state while preserving exactly one journal read and performing no replay.
  - Both cases retain one used original grant, result=null, no result artifact or result decision, exact marker refusal on replacement issue, and no replacement grant ID.
requirements: |
  - Stage 5 production-only scope: SATISFIED; only practical_agency/controller.py and practical_agency/state_machine.py are changed.
  - Persist execution attempt and owner at begin: SATISFIED by event.event_id and process_instance_id stored in the durable invocation record before observation.
  - Replacement-process pathless orphan recovery: SATISFIED before any receipt, drift, descriptor, or target inspection.
  - Never infer zero or completed effect: SATISFIED; every orphan becomes execution_state=unknown.
  - Durable blocked mission and exact marker in both collections: SATISFIED.
  - Preserve used grant and null result: SATISFIED.
  - No fabricated result, observed effect, artifact, or result decision: SATISFIED.
  - Original-grant non-replayability: SATISFIED by the unknown-marker execute guard in addition to the already consumed durable grant.
  - Replacement issue/execute refusal without target observation: SATISFIED by pre-descriptor and pre-execution marker guards.
  - Remain blocked until future external-receipt reconciliation: SATISFIED by reconciliation-protected generic unblock behavior and the absence of any new clearing transition.
  - Preserve the 13 pre-existing focused controls: SOURCE-PRESERVED; the new behavior is additive at begin and otherwise marker-gated. Runtime verification remains with the origin.
  - MCP request schema, capability discovery, web, proof integration, and principal independence: INTENTIONALLY UNCHANGED.
  - Overall status remains PARTIAL because the independent Stage 3 findings excluded from Stage 5 remain unresolved.
decisions_and_assumptions: |
  - MissionEvent.event_id is the execution-attempt identity. It is unique, revision-bound, already part of the closed event envelope, and is additionally stored on the invocation record for direct recovery inspection.
  - ManifestController.process_instance_id is the execution-owner identity. A different or absent owner on replacement engagement is treated conservatively as orphaned.
  - An unresolved capability-effect marker blocks all canonical capability issuance and execution, rather than attempting an unproven same-return-point equivalence calculation.
  - Recovery checkpoints each unknown transition immediately so the checkpoint store's existing same-revision collision behavior remains the concurrency guard; recovery does not skip intermediate revisions.
  - Cancellation or authority revocation remains available to the operator, but ordinary unblocking cannot claim reconciliation.
  - No external receipt is inferred from the checkpoint, target contents, observation count, process exit code, or owner disappearance.
blockers_or_questions: NONE
recommended_next_action: Apply this diff unchanged and verify it with python -m unittest tests.test_durable_capability_transaction -v as the single Stage 5 origin check.
