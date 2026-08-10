schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0001
stage: 1-red-tests
prepared_utc: 2026-08-10T05:35:46Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: e07b75b5-7c6d-4292-9596-746f34a9f738
submission_policy: one prompt-only submission; no attachments; tests-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=e07b75b5-7c6d-4292-9596-746f34a9f738]

ROLE
Act as the test architect for a security-sensitive durable capability transaction. You have advisory patch authority only.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 1 only: produce the focused adversarial RED tests as a tests-only unified diff. Do not provide production code.

CONTEXT AND EVIDENCE
The durable repository handoff and its linked prior review are the complete context. Use only repository content at the exact packet commit. No attachments.

CONSTRAINTS
Do not modify, execute, publish, merge, or message anyone. Do not claim tests were run. Each test must name a reachable defect, exercise real controller/MCP/checkpoint behavior, and assert zero underlying effect for refusal paths. No production hunks.

OUTPUT CONTRACT
Return only the outsource-relay@1 envelope defined in HANDOFF.md, with based_on_commit set to {packet_commit} and status PARTIAL unless genuinely BLOCKED or QUESTION. Put the complete tests-only unified diff in work_product.
```
