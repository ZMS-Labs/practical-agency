schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0008
stage: 4-orphaned-execution-tests
prepared_utc: 2026-08-10T08:50:56Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 0c5a26c8-312c-44bf-a26d-e5f67fc089f9
submission_policy: one prompt-only submission; no attachments; tests-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=0c5a26c8-312c-44bf-a26d-e5f67fc089f9]

ROLE
Act as the test author for Practical Agency's fail-closed orphaned capability execution boundary.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 4 only. Read the preserved Stage 3 review, exact source, and existing focused tests at that commit. Return the smallest tests-only unified diff that proves the two forced-exit cases and every durable recovery/refusal property required by Stage 4.

CONSTRAINTS
Do not modify production code. Do not address the MCP schema, discovery, web, proof integration, or principal findings in this stage. Do not execute, publish, merge, message anyone, or claim tests were run. Use real subprocesses, the real checkpoint store, pathless replacement-process engagement, and an observation side effect that distinguishes zero reads from exactly one read. The patch must be directly applicable to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Include the tests-only unified diff in work_product, a test-to-defect matrix with expected RED failures in evidence, and one next action for the origin. No prose before or after the fence and no nested fences.
```
