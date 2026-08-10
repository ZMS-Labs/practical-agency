schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: b037f4d8733fd5e76b4d0bde431532a17b4478c6
status: PARTIAL
summary: |
  Stage 7 production-only patch gives manifest_capability_issue an exact closed nested intent schema matching the controller contract. The existing recursive MCP validator can therefore admit the committed valid issue frame while rejecting missing, mistyped, empty-list, or unexpected nested request fields before controller dispatch. The execute schema and validator remain unchanged, preserving the protocol refusal for object-valued evidence_payload entries and admitting the committed valid file.read execute frame, which omits that optional payload. Tests were not run.
work_product: |
  diff --git a/practical_agency/mcp_server.py b/practical_agency/mcp_server.py
  --- a/practical_agency/mcp_server.py
  +++ b/practical_agency/mcp_server.py
  @@ -19,6 +19,24 @@ STRING_LIST = {
       "minItems": 1,
       "items": {"type": "string", "minLength": 1},
   }
  +CAPABILITY_INTENT_SCHEMA = {
  +    "type": "object",
  +    "additionalProperties": False,
  +    "required": [
  +        "bounded_question_or_action",
  +        "requested_permissions",
  +        "requested_effects",
  +        "estimated_costs",
  +        "timeout_or_stop_condition",
  +    ],
  +    "properties": {
  +        "bounded_question_or_action": {"type": "string", "minLength": 1},
  +        "requested_permissions": STRING_LIST,
  +        "requested_effects": STRING_LIST,
  +        "estimated_costs": STRING_LIST,
  +        "timeout_or_stop_condition": {"type": "string", "minLength": 1},
  +    },
  +}
   DEFINITION_SCHEMA = {
       "type": "object",
       "additionalProperties": False,
  @@ -81,7 +99,7 @@ TOOLS = [
       {
           "name": "manifest_capability_issue",
           "description": "Discover one current descriptor and issue one exact mission-bound grant.",
  -        "inputSchema": _closed_schema({"capability_id": {"type": "string", "minLength": 1}, "blocking_condition": {"type": "string", "minLength": 1}, "admitted_operation": {"type": "string", "minLength": 1}, "evidence_scope": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}, "request": {"type": "object"}}, ("capability_id", "blocking_condition", "admitted_operation", "evidence_scope", "request")),
  +        "inputSchema": _closed_schema({"capability_id": {"type": "string", "minLength": 1}, "blocking_condition": {"type": "string", "minLength": 1}, "admitted_operation": {"type": "string", "minLength": 1}, "evidence_scope": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}, "request": CAPABILITY_INTENT_SCHEMA}, ("capability_id", "blocking_condition", "admitted_operation", "evidence_scope", "request")),
       },
       {
           "name": "manifest_capability_execute",
evidence: |
  REQUIREMENT-TO-HUNK MAP — source analysis only; no execution claims.

  1. Valid nested manifest_capability_issue frame — hunks 1 and 2:
     CAPABILITY_INTENT_SCHEMA declares exactly the five fields required by ManifestController.manifest_capability_issue: bounded_question_or_action, requested_permissions, requested_effects, estimated_costs, and timeout_or_stop_condition. Its scalar and list shapes match the controller's _nonempty and _nonempty_string_list checks. Wiring that schema into the actual tool declaration lets the existing _validate recursion accept the committed nonempty intent instead of encountering an object with no declared properties.

  2. Unexpected nested request fields remain protocol refusals — hunks 1 and 2:
     additionalProperties is explicitly false. McpServer._call_tool invokes _validate before getattr/controller dispatch, so unexpected_nested_field fails at the protocol boundary before host binding, checkpoint persistence, or target observation.

  3. Object-valued evidence_payload entries remain protocol refusals — narrow scope of hunk 2:
     The patch changes only the issue tool's request member. It does not alter manifest_capability_execute, its evidence_payload schema, _validate, or _call_tool ordering. Under the preserved validator, a nonempty evidence_payload member has no declared nested property and is rejected before the controller. The committed valid file.read execute frame carries no evidence_payload and remains admissible.

  4. No generic nested-object opening or controller-deferred shape validation — both hunks:
     The repair supplies a field-complete closed schema rather than changing _validate to accept undeclared object members. Semantic authority checks remain in the controller, while malformed structure remains an MCP_PROTOCOL_ERROR.

  5. Production-only and non-goal preservation — complete diff:
     The only modified path is practical_agency/mcp_server.py. There are no controller, discovery, capability execution, web, mission-proof, principal, orphan-recovery, shell, mutation, or test changes.
requirements: |
  - Stage 7 production-only boundary: satisfied by a one-file MCP schema patch.
  - DCT-005 / strict runtime objects: the real stdio path can reach the existing canonical request/result producer for validation by the committed Stage 6 test.
  - DCT-008 / bounded positive local read: the valid dynamic-reader issue frame can traverse MCP so its returned grant_id can be executed once by the existing file.read path.
  - DCT-009 / real MCP boundary: malformed nested request and evidence shapes remain rejected by _validate before controller dispatch.
  - Verification state: open and origin-owned; no GREEN, focused-suite, or full-suite claim is made.
decisions_and_assumptions: |
  - The controller's exact five-field capability intent is authoritative for the nested MCP request shape.
  - Existing STRING_LIST and _validate behavior are reused rather than adding a second validator path or broadening object semantics.
  - Positive nonempty evidence_payload support is outside Stage 7: web remains disabled, the committed valid local-read frame omits the optional payload, and the malformed object-valued case must remain closed.
blockers_or_questions: NONE
recommended_next_action: Apply this diff and run python -m unittest tests.test_durable_capability_transaction.DurableCapabilityTransactionRedTests.test_real_stdio_mcp_issue_execute_round_trip_and_nested_fields_fail_closed -v.
