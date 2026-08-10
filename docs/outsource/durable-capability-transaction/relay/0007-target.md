schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 962eff4a54913cba7d0b6a735f4392759494a847
status: PARTIAL
summary: |
  Stage 3 verdict: NO-GO for using the durable capability transaction in the live three-capability single-invocation proof.

  Stage 2 materially improved the original path: execution now loads the canonical grant by grant_id, rechecks descriptor and mission authority, consumes durable one-use authority before target observation, emits strict request/result objects, removes caller grant/request/result injection from the listed MCP tools, refuses web operations before resolver or network activity, and durably preserves FAIL and INCONCLUSIVE verdicts.

  The transaction is nevertheless not interruption-safe. Once begin_capability_execution has been checkpointed, the same durable state represents all three possibilities: the operation never started, the observation completed but its result was not checkpointed, or its effect is unknown. Pathless resume has no receipt or transition capable of distinguishing those states without replay, does not mark the transaction unknown, and does not block issuance of a replacement grant. There are also independent live-proof blockers: a valid capability request cannot pass the MCP validator, the production runtime discovers no eligible capability descriptor beyond manifest itself, web remains intentionally disabled, and successful capability results are not integrated into mission contradiction or typed-verification logic.

  This was a source and architecture review only. No tests, subprocess probes, network requests, repository mutations, publications, merges, or external messages were performed.
work_product: |
  VERDICT: NO-GO

  SEVERITY-ORDERED FINDINGS

  1. CRITICAL — A checkpointed in-progress transaction is irrecoverably ambiguous and does not fail closed.

     The execution sequence is:

     a. ManifestController.manifest_capability_execute loads the canonical pending record and creates a deep copy of its grant.
     b. state_machine.begin_capability_execution calls consume_grant on the durable grant, setting used=true, changes execution_state from pending to in_progress, and records capability-execution-begun.
     c. The controller saves that revised manifest before calling execute_read.
     d. Only after execute_read returns does the controller create capability-result@1, apply record_capability_result, set execution_state=consumed, and save another checkpoint.

     If the process ends after step c, the latest discoverable checkpoint always contains used=true, execution_state=in_progress, and result=null. That representation is identical when:

     - the process ended before execute_read performed any observation;
     - the file was read but the process ended before the result event;
     - the operation was interrupted at an unknowable point.

     FileCheckpointStore.load_latest and discover_active_mission correctly recover that checkpoint, but manifest_engage examines filesystem-artifact receipts and governed-workspace drift only; it does not inspect capability execution_state. It therefore returns the mission as active with its prior frontier and no capability-unknown blocker. Re-executing the same grant is refused as CAPABILITY_EXECUTION_IN_PROGRESS, but there is no closed transition to unknown, abandoned, reconciled, or failed. More seriously, manifest_capability_issue does not refuse while an earlier transaction is in_progress, so a caller can mint a new grant for the same target and semantically replay the observation under a new grant ID.

     Ordinary post-begin errors have the same defect without process death. READ_TARGET_NOT_FOUND, path-validation failures, decoding failures, result-construction failures, or final-checkpoint failures can leave the durable transaction permanently in_progress after zero or completed observation.

     Current checkpoint state therefore cannot safely distinguish zero effect, completed effect, and unknown effect. Without a durable operation receipt or an atomic effect/result substrate, the only honest resume classification is unknown and blocked; it must not reset to pending or silently retry.

     Citations:
     - practical_agency/controller.py::ManifestController.manifest_capability_execute
     - practical_agency/controller.py::ManifestController.manifest_engage
     - practical_agency/controller.py::ManifestController.manifest_capability_issue
     - practical_agency/state_machine.py::apply_event, begin_capability_execution branch
     - practical_agency/state_machine.py::apply_event, record_capability_result branch
     - practical_agency/capability_grants.py::consume_grant
     - practical_agency/checkpoint_store.py::FileCheckpointStore.save and load_latest
     - practical_agency/mission_repository.py::discover_active_mission

  2. CRITICAL — No valid capability-issuance payload can traverse the current MCP surface.

     The manifest_capability_issue MCP schema declares request only as {"type": "object"}, with no nested properties. The custom _validate implementation does not implement normal JSON Schema open-object behavior: for every supplied object member it requires the key to exist in schema["properties"]. Because request has no properties, every nonempty request is rejected as MCP_PROTOCOL_ERROR.

     An empty request passes that nested validator but is then rejected by ManifestController.manifest_capability_issue, which requires exactly bounded_question_or_action, requested_permissions, requested_effects, estimated_costs, and timeout_or_stop_condition. Consequently there is no request value accepted by both MCP and the controller.

     The same validator behavior makes nonempty evidence_payload objects impossible, although that is presently dormant because web operations are disabled.

     The positive tests call ManifestController.manifest_capability_issue directly. The MCP tests initialize, list tools, engage, and exercise malformed or refused calls, but contain no successful MCP capability issue/execute round trip. Passing those tests would not contradict this source-level impossibility.

     Citations:
     - practical_agency/mcp_server.py::TOOLS, manifest_capability_issue inputSchema
     - practical_agency/mcp_server.py::_validate
     - practical_agency/mcp_server.py::McpServer._call_tool
     - practical_agency/controller.py::ManifestController.manifest_capability_issue
     - tests/test_mcp_server.py::McpServerProcessTests
     - tests/test_durable_capability_transaction.py::DurableCapabilityTransactionRedTests._issue

  3. CRITICAL — The exact installed package has no eligible member capability, and the requested three-capability proof is not executable.

     ManifestController._descriptor discovers only FileSystemSkillProvider(self.plugin_root / "skills"). At this commit, that directory contains only skills/manifest. Its descriptor declares mission-manifest and checkpoint contracts, not capability-request@1 and capability-result@1, so manifest_capability_issue rejects it with CAPABILITY_CONTRACT_MISMATCH.

     The focused tests and probe scripts manufacture skills/dynamic-reader/SKILL.md inside temporary copied runtimes. No production provider discovers other installed plugin roots, host capability descriptors, or a federated registry. manifest_engage does not discover or select a capability; the caller must supply capability_id.

     Even the manufactured descriptor is not invoked. The controller ignores its method body and always calls the built-in generic execute_read. Descriptor kind, persistence, and independence do not govern dispatch. resource.read is only a resource:-prefixed alias for another workspace file read, not a distinct resource provider. The third test class, web.open, is intentionally refused by both issue and execute before network access.

     The current package therefore has zero eligible production DCT members, two built-in local read spellings rather than independently invoked capabilities, and no reachable web member. It cannot support a live three-capability single-invocation proof.

     Citations:
     - practical_agency/controller.py::ManifestController._descriptor
     - practical_agency/controller.py::ManifestController.manifest_capability_issue
     - practical_agency/controller.py::ManifestController.manifest_capability_execute
     - practical_agency/capability_discovery.py::FileSystemSkillProvider and CapabilityDescriptor
     - practical_agency/capability_operations.py::execute_read
     - skills/manifest/SKILL.md frontmatter
     - committed skills/ tree
     - tests/test_durable_capability_transaction.py::DurableCapabilityTransactionRedTests._runtime
     - tests/test_three_capability_interruption.py::ThreeCapabilityInterruptionTests
     - scripts/run_capability_controller_probe.py
     - scripts/run_capability_process_probe.py

  4. HIGH — Execute-time strings are grant-constrained, but the actual observation target and cost are not fully transaction-bound.

     The successful Stage 2 path does prevent execute-time argument substitution: operation must equal grant.admitted_operation, target must be the sole evidence_scope member, evidence_refs must remain within that scope, the canonical request must encode the same operation and target, the descriptor digest must still match, and mission authority is rechecked. No caller-provided execute argument was found that can widen the stored grant at the value level.

     Two material limits remain:

     - Issuance remains caller-selected. capability_id, admitted_operation, evidence_scope, blocking_condition, and the request intent all originate in the tool call. The descriptor supplies identity, contracts, and extra permission strings but does not determine the operation or target. blocking_condition is not required to equal the current frontier, and authorize_action explicitly discards capability_id. This is canonicalization of caller routing, not manifest selection of a capability that owns the blocker.
     - _canonical_relative validates a pathname and then execute_read later calls is_file and read_text through that pathname. A concurrent replacement between resolution and open can substitute a symlink or reparse target after validation. There is no descriptor-relative or no-follow file open binding the observed inode to the authorized path.
     - timeout_or_stop_condition is recorded but never enforced. File and resource reads load the complete UTF-8 contents into memory and then into the durable manifest without a byte limit. The symbolic cost "bounded reads" is therefore not implemented as an actual bound.

     The canonical grant binds strings, but not the exact filesystem object observed or a measurable read limit.

     Citations:
     - practical_agency/controller.py::ManifestController.manifest_capability_issue
     - practical_agency/controller.py::ManifestController.manifest_capability_execute
     - practical_agency/authority.py::authorize_action
     - practical_agency/capability_operations.py::_canonical_relative
     - practical_agency/capability_operations.py::execute_read
     - practical_agency/capability_discovery.py::CapabilityDescriptor
     - contracts/capability-request.schema.json::timeout_or_stop_condition

  5. HIGH — A strict capability result is durable audit data, but it is not yet load-bearing typed proof or contradiction-aware mission state.

     The successful controller path now persists objects that satisfy the strict capability request and result schemas. That is a genuine improvement.

     record_capability_result, however, only stores the result, changes execution_state to consumed, appends capability-result:<grant_id> to durable_artifacts, and adds a decision record. It does not:

     - add or update a verified fact;
     - clear the blocking condition or advance the frontier;
     - bind the result to continuity.execution_receipts;
     - create a VerifierResult;
     - make the result eligible for _missing_proof_refs or manifest_accept;
     - re-observe the capability target during manifest_engage;
     - invalidate the result when the source later changes.

     manifest_accept derives evidence only from verified verifier results bound to execution receipts. Capability results are not among those qualifying records. The current three-capability test completes only after record_fixture_verifier_result fabricates a separate proof path.

     The test named test_three_classes_survive_restart_and_retain_typed_results also remains on the legacy route: it records {"operation": operation} rather than capability-request@1, clones a manifest in the same process rather than using checkpoint discovery, invokes execute_read directly, records the old grant-shaped result through the execution_state-is-absent branch, mocks web retrieval, and injects a fixture verifier before acceptance. The process probe is statically incompatible with the current controller signature, request contract, descriptor contract checks, and web refusal.

     The implementation therefore retains strict DCT result shape on one successful controller path, but has not connected that result to contradiction handling, mission progress, whole-mission typed proof, or the claimed process/single-invocation proof.

     Citations:
     - practical_agency/state_machine.py::apply_event, record_capability_result branch
     - practical_agency/state_machine.py::_missing_proof_refs
     - practical_agency/controller.py::ManifestController.manifest_engage
     - practical_agency/controller.py::ManifestController.manifest_accept
     - contracts/capability-request.schema.json
     - contracts/capability-result.schema.json
     - tests/test_durable_capability_transaction.py::test_persisted_request_and_result_cannot_violate_strict_schemas
     - tests/test_three_capability_interruption.py::ThreeCapabilityInterruptionTests
     - scripts/run_capability_process_probe.py

  6. MEDIUM — Direct request/result injection is closed at MCP but remains reachable through the public Python controller and legacy state-machine branch.

     manifest_capability_request and manifest_capability_result remain public ManifestController methods. They are absent from TOOLS, and an arbitrary tools/call name is rejected before getattr, so no current MCP injection route was found.

     In-process callers can nevertheless invoke manifest_capability_request with a caller-supplied grant and an untyped request. state_machine.record_capability_request stores such a record without execution_state. manifest_capability_result can then use state_machine.record_capability_result's legacy branch, which requires only a matching return point and nonempty result.evidence_refs rather than a begun execution or the strict result fields.

     Existing tests and scripts actively exercise this compatibility path. It does not establish a current remote MCP exploit, and injected capability results do not independently satisfy mission completion, but it contradicts any package-wide claim that only the canonical internal executor can create capability requests and results.

     Citations:
     - practical_agency/controller.py::ManifestController.manifest_capability_request
     - practical_agency/controller.py::ManifestController.manifest_capability_result
     - practical_agency/state_machine.py::apply_event, record_capability_request branch
     - practical_agency/state_machine.py::apply_event, record_capability_result legacy branch
     - practical_agency/mcp_server.py::TOOLS and McpServer._call_tool
     - tests/test_three_capability_interruption.py
     - tests/test_durable_capability_transaction.py::test_mcp_direct_request_injection_refuses_before_checkpoint_change
     - tests/test_durable_capability_transaction.py::test_mcp_direct_result_injection_refuses_before_checkpoint_change

  7. HIGH ASSURANCE GAP / MEDIUM ROLE-MODEL DEFECT — Negative verdict evidence is fail-closed, but distinct-principal acceptance is unavailable and capability workers are absent from the worker exclusion set.

     No zero-evidence negative-verdict bypass was found on the current controller path. manifest_accept derives evidence from verified results tied to completed execution receipts; reject requires FAIL or INCONCLUSIVE, a nonempty reason, nonempty evidence_refs, and coverage_limits; it leaves the mission non-completed and records the unresolved verdict.

     Declared-role acceptance also checks that actor_ref equals the configured completion_acceptor and is not in _material_workers. The normal filesystem-artifact path records mission-steward as a material-action actor, so that exact actor is refused.

     This is not distinct-principal proof. acceptor_ref is supplied by the same MCP caller and is not authenticated. _acceptance_assurance deliberately refuses externally-proven because no principal verifier exists. Any live result must therefore remain labelled declared-role-separation.

     There is also a forward integration defect: _material_workers recognizes only decisions whose kind is material-action. It does not include capability-request, capability-execution-begun, or capability-result actors. If DCT capability work is later permitted to bear material completion load, mission-steward:capability will not be classified as a worker. Definition and manifest validation also permit any nonempty completion_acceptor string, including steward-labelled values. The current guard must be expanded before capability execution can support a no-steward-self-certification claim.

     Citations:
     - practical_agency/controller.py::ManifestController.manifest_accept
     - practical_agency/state_machine.py::_material_workers
     - practical_agency/state_machine.py::_require_independent_acceptor
     - practical_agency/state_machine.py::_acceptance_evidence
     - practical_agency/state_machine.py::_acceptance_assurance
     - practical_agency/state_machine.py::accept and reject branches
     - practical_agency/validation.py::validate_manifest_dict
     - contracts/mission-manifest.schema.json::integrity.completion_acceptor
     - AGENTS.md::Invariants
     - skills/manifest/SKILL.md::Guardrail claim ceiling

  CONTROLS THAT SURVIVED SCRUTINY

  - Canonical grant lookup by grant_id is implemented; caller-carried grant JSON is not accepted by manifest_capability_execute.
  - Operation, target, request identity, evidence references, mission revision, descriptor digest, permission, protected-state, symbolic cost, and escalation checks all occur before the intended target read on the current controller path.
  - The stored grant is marked used and in_progress before execute_read.
  - A completed result prevents same-grant replay across controller replacement.
  - manifest_capability_request and manifest_capability_result are absent from the listed MCP tools, and unknown tool names fail protocol validation.
  - web.* is refused in both issue and execute before _retrieve_web, DNS resolution, or urllib access.
  - The successful canonical request/result producer path is stricter than the committed schemas and persists request/result identity.
  - FAIL and INCONCLUSIVE require evidence, reason, and coverage and remain non-completed.
  - Current capability grants require mutation=false; no generic shell or capability mutation path was introduced.
  - The hook preserves dispatcher-only mutation for covered host tools while the mission lock is active. This is host-covered posture, not OS-level non-bypassability.
evidence: |
  SOURCE-IMPLEMENTED AND POSITIVELY SUPPORTED

  DCT canonical transaction:
  - practical_agency/controller.py::ManifestController.manifest_capability_issue
  - practical_agency/controller.py::ManifestController.manifest_capability_execute
  - practical_agency/state_machine.py::record_capability_request, begin_capability_execution, record_capability_result
  - practical_agency/capability_grants.py::issue_grant_from_descriptor and consume_grant

  Pre-observation authority:
  - practical_agency/authority.py::authorize_action
  - practical_agency/controller.py::_observed_descriptor
  - practical_agency/capability_operations.py::execute_read
  - tests/test_durable_capability_transaction.py::test_forged_same_id_wider_scope_refuses_before_file_observation
  - tests/test_durable_capability_transaction.py::test_stale_descriptor_refuses_before_file_observation
  - tests/test_durable_capability_transaction.py::test_missing_authority_refuses_before_file_observation

  MCP injection and web refusal:
  - practical_agency/mcp_server.py::TOOLS and McpServer._call_tool
  - tests/test_durable_capability_transaction.py::test_mcp_tool_list_removes_injection_surfaces_and_caller_grant
  - tests/test_durable_capability_transaction.py::test_mcp_caller_grant_refuses_before_file_or_checkpoint_effect
  - tests/test_durable_capability_transaction.py::test_mcp_direct_request_injection_refuses_before_checkpoint_change
  - tests/test_durable_capability_transaction.py::test_mcp_direct_result_injection_refuses_before_checkpoint_change
  - tests/test_durable_capability_transaction.py::test_web_operation_refuses_before_retrieval_resolution_or_network

  Strict objects and negative verdicts:
  - contracts/capability-request.schema.json
  - contracts/capability-result.schema.json
  - tests/test_durable_capability_transaction.py::test_persisted_request_and_result_cannot_violate_strict_schemas
  - tests/test_durable_capability_transaction.py::test_independent_fail_verdict_is_durable_without_completion
  - tests/test_durable_capability_transaction.py::test_independent_inconclusive_verdict_is_durable_without_completion

  SOURCE-CONTRADICTED OR UNEXERCISED

  Crash-window recovery:
  - No committed test terminates after the begun checkpoint and before result persistence.
  - No production transition represents execution_state=unknown.
  - manifest_engage has no capability-transaction reconciliation branch.
  - New grant issuance is not blocked by an existing in_progress transaction.

  Positive MCP DCT:
  - tests/test_mcp_server.py has no successful manifest_capability_issue or manifest_capability_execute call.
  - The current request input schema and custom validator admit no request accepted by the controller.

  Production discovery and invocation:
  - practical_agency/controller.py::_descriptor scans only plugin_root/skills.
  - The exact skills tree contains only manifest, whose contracts are not DCT contracts.
  - Test and probe descriptors are manufactured in temporary runtimes.
  - No member capability implementation is invoked; execute_read owns the method and verdict.

  Contradiction and proof:
  - manifest_engage reconciles filesystem execution receipts and governed-workspace drift, not capability results.
  - manifest_accept consumes VerifierResult records tied to execution receipts, not capability-result@1 records.
  - tests/test_three_capability_interruption.py relies on the legacy untyped path and fixture proof.

  Distinct principal:
  - externally-proven acceptance always refuses because a principal verifier is unavailable.
  - Current evidence establishes declared-role separation only.

  PRIOR-RELAY COMPARISON

  docs/outsource/manifest-capability-orchestration-review/relay/0002-target.md correctly identified caller-carried grants, post-observation grant consumption, missing mission authority, MCP injection, schema mismatch, active web transport, and missing negative-verdict controller flow. Stage 2 fixed those defects on the canonical controller/MCP path.

  docs/outsource/durable-capability-transaction/relay/0003-target.md added the 13 focused adversarial tests, but no crash-after-begin test or positive MCP issuance test.

  docs/outsource/durable-capability-transaction/relay/0005-target.md introduced pending -> in_progress -> consumed and durable pre-observation consumption. It did not add the unknown/reconciliation half of the state model identified as open in the handoff.

  docs/outsource/durable-capability-transaction/relay/0006-origin.md requests the present Stage 3 review and does not itself supply implementation evidence.

  The Stage 3 handoff attributes green focused and repository gates to the origin. Those reports were not independently rerun here and do not exercise the untested paths above.
requirements: |
  DCT-001: HISTORICAL / NOT RE-EXECUTED. The committed Stage 1 work product is tests-only. This Stage 3 review did not run or alter it.

  DCT-002: PARTIALLY SATISFIED. Forged grant values, wider scope, stale descriptor, and named authority failures are checked before the intended target read. Exact target identity remains vulnerable to pathname replacement between validation and open, and the read has no actual byte/time bound.

  DCT-003: SATISFIED ONLY AFTER A RESULT IS DURABLY RECORDED; CONTRADICTED FOR THE REQUIRED CRASH WINDOW. A fully completed grant cannot produce a second observation after controller replacement. A persisted in_progress transaction cannot be classified, and the same observation can be repeated through a newly issued grant.

  DCT-004: SATISFIED AT THE LISTED MCP SURFACE; PARTIAL PACKAGE-WIDE. Caller grant/request/result injection tools are absent from MCP. Public Python controller methods and the legacy state-machine branch still accept caller records.

  DCT-005: SATISFIED FOR THE NEW CANONICAL SUCCESS PATH. Persisted canonical requests and results match their strict schemas. Legacy records remain accepted outside that path, and strict capability results are not whole-mission verifier proof.

  DCT-006: SATISFIED. Web operations fail before resolver or network access. This also means the proposed live web/third-capability proof is presently unavailable.

  DCT-007: SATISFIED AT DECLARED-ROLE ASSURANCE. FAIL and INCONCLUSIVE are durably represented with reason, evidence, and coverage and cannot complete the mission. Authenticated principal independence remains unavailable.

  DCT-008: SATISFIED THROUGH DIRECT CONTROLLER CALLS; CONTRADICTED THROUGH THE ACTUAL MCP ISSUE SURFACE. The local read transaction can execute once when tests call the controller directly, but no valid issue request can pass MCP validation.

  DCT-009: PARTIAL. The focused module exercises real controller, checkpoint, state-machine, and negative MCP boundaries, but does not exercise a positive MCP transaction or the begin/result process-death window. The older three-capability test and process probes use legacy, manufactured, mocked, or now-incompatible paths.

  ACTIVE SINGLE-INVOCATION REQUIREMENTS

  Interruption survival: NO. Pathless recovery loads the checkpoint but cannot safely resume or classify an orphaned execution.

  Contradiction handling: NO for capability results. Filesystem-artifact receipts are reconciled; capability observations are not re-anchored.

  Typed proof: PARTIAL. Strict capability request/result shape is implemented, but the result is not bound into execution-receipt/VerifierResult completion proof.

  Dispatcher-only mutation: YES within the covered MCP/hook boundary. DCT operations are read-only and mutation remains on manifest_dispatch. Universal non-bypassability is not proven.

  Dynamic member-capability ownership: NO. Production discovery finds no eligible member, caller routing remains explicit, and the generic executor absorbs the method.

  Three-capability availability: NO. Only local file/resource aliases are implemented through the controller; web is disabled.

  Distinct principal: NO. Only declared-role separation is implemented, and capability worker actors are not included in material-worker accounting.

  Overall live-proof requirement: CONTRADICTED. Multiple independent source-level blockers remain; passing current tests is not sufficient evidence for the requested proof.
decisions_and_assumptions: |
  - Decision: NO-GO applies specifically to using this DCT in the live three-capability single-invocation proof at commit 962eff4a54913cba7d0b6a735f4392759494a847.
  - Decision: Web refusal is treated as the correct Stage 2 security boundary, not as evidence that web capability execution is ready.
  - Decision: Execute-time operation, target, and evidence strings are considered canonical-grant constrained; issue-time caller selection, filesystem object substitution, and unbounded reads are reported separately rather than mislabelled as same-ID grant forgery.
  - Decision: An orphaned in_progress operation must be classified unknown unless a trustworthy external receipt proves a narrower state. Re-observation is not evidence that the first observation did or did not occur.
  - Assumption: The active three-capability target is the file.read, resource.read, and web.open shape represented by the committed three-capability test and probes.
  - Assumption: Public Python controller methods are reachable to in-process package consumers but are outside the currently listed remote MCP surface; findings distinguish those boundaries.
  - Claim ceiling: No runtime, test, or principal-authentication proof was independently performed. Source evidence supports declared-role separation only.
blockers_or_questions: |
  BLOCKERS:

  1. No fail-closed reconciliation for a persisted in_progress capability execution.
  2. No valid manifest_capability_issue request can pass the MCP validator.
  3. No eligible production member capability is discoverable from the exact installed skill root.
  4. The controller does not dynamically select or invoke a capability that owns the blocker.
  5. Web is intentionally disabled, so the third committed capability class cannot run.
  6. Capability results do not participate in contradiction reconciliation or typed mission verification.
  7. Distinct-principal acceptance is unavailable; capability worker identities are not included in material-worker exclusion.
  8. The positive process and three-capability evidence is legacy, manufactured, mocked, or incompatible with the current API.

  QUESTIONS: NONE. These defects do not require an operator architecture choice before the first repair; fail-closed unknown handling is the clear default.
recommended_next_action: |
  Make one test-first orphaned-execution patch before any additional live proof.

  Add a focused subprocess test with two forced exits against one canonical local-read transaction:

  - Case A exits from execute_read without reading, after the begun checkpoint exists.
  - Case B reads the target exactly once and exits before record_capability_result.
  - A replacement controller engages pathlessly in each case.

  Both cases must produce the same honest outcome: a durable execution_state=unknown transaction, mission status blocked, a named CAPABILITY_EFFECT_UNKNOWN:<grant_id> blocker/unresolved marker, the original grant remaining non-replayable, no fabricated capability result, zero additional target observations, and refusal to issue or execute another grant for the same unresolved return point.

  Implement only the closed recovery behavior demanded by that test: persist an execution-attempt/owner identity at begin, detect an orphaned in_progress attempt on replacement-process engagement, transition it to unknown, and require an external receipt or explicit authorized reconciliation before it can be resolved. Never reset it to pending and never infer completed or zero effect from the checkpoint alone.

  Do not enable web, broaden discovery, add a shell or mutation adapter, or spend the live three-capability proof in this patch. The MCP request-schema and production-discovery blockers remain separate required repairs after the crash boundary is fail-closed.
