schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0010
stage: 5-orphaned-execution-implementation
prepared_utc: 2026-08-10T09:28:24Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 92b7add8-2a5b-4538-ba04-ad28f2c43223
submission_policy: one prompt-only submission; no attachments; production-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=92b7add8-2a5b-4538-ba04-ad28f2c43223]

ROLE
Act as the implementation author for Practical Agency's fail-closed orphaned capability execution boundary.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 5 only. Read the exact Stage 4 tests, preserved relays, controller, state machine, validation model, and checkpoint/discovery code at that commit. Return the smallest production-only unified diff that makes the two committed RED orphaned-execution tests GREEN while preserving the 13 existing focused controls.

VERIFIED RED
The origin ran python -m unittest tests.test_durable_capability_transaction -v. All 15 tests executed. The 13 pre-existing tests passed. Only test_orphaned_execution_before_target_read_fails_closed and test_orphaned_execution_after_one_target_read_fails_closed failed at the shared expected durable outcome: no recovery checkpoint was created and the transaction remained in_progress without the required unknown marker and replacement guard.

CONSTRAINTS
Do not modify tests. Do not address MCP request schema, capability discovery, web, proof integration, or principal independence in this stage. Do not execute, publish, merge, message anyone, or claim tests were run. Never infer zero or completed effect from the checkpoint; orphan recovery must classify unknown and remain blocked until a future external-receipt reconciliation contract exists. The patch must apply directly to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the production-only unified diff in work_product, map requirements to hunks in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
