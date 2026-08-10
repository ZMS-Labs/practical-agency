schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0018
stage: 9-host-member-tests
prepared_utc: 2026-08-10T11:00:44Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: e0067b19-8162-4f97-a062-57686c1065c4
submission_policy: one prompt-only submission; no attachments; tests-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=e0067b19-8162-4f97-a062-57686c1065c4]

ROLE
Act as the test author for Practical Agency's host-attested external member-capability transaction.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 9 only. Read the Stage 8 architecture relay and exact current controller, state machine, contracts, host evidence, discovery, and focused fixtures. Return exactly one smallest tests-only RED vertical slice named test_host_member_is_selected_from_durable_blocker_and_receipt_bound.

REQUIRED TEST EVIDENCE
Inject a fake implementation of the exact reserved host catalog/invoke/lookup protocol. Derive one typed durable need from the mission blocker; expose one separately rooted non-mutating member; issue with no caller selection fields; execute with grant_id only; invoke the fake member once; prove execute_read is never entered; preserve the member's strict FAIL result and coverage byte-for-byte; and prove durable binding among need, owner/runtime, descriptor/contracts, invocation_ref, grant, request, execution attempt, receipt, result, and exact return point. Also prove absent host registry fails closed with HOST_CAPABILITY_REGISTRY_UNAVAILABLE before state or observation change.

CONSTRAINTS
Tests only. Do not modify production or existing tests, simulate a real Codex adapter, use caller roots/handles/results, enable web, integrate whole-mission proof, alter principal handling, add shell/mutation, execute, publish, merge, message anyone, or claim tests were run. The patch must apply directly to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the tests-only unified diff in work_product, include a test-to-defect matrix and expected RED failures in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
