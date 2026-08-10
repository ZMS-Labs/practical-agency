schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0006
stage: 3-independent-review
prepared_utc: 2026-08-10T08:25:13Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 5799cf03-625b-4de5-92f3-90307e639d95
submission_policy: one prompt-only submission; no attachments; review-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=5799cf03-625b-4de5-92f3-90307e639d95]

ROLE
Act as the independent security and architecture reviewer for Practical Agency's durable capability transaction and its role in the single-invocation manifest contract.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 3 only: inspect the exact implementation, tests, schemas, MCP surface, checkpoint behavior, and prior relays. Return a GO or NO-GO verdict for using this transaction in the live three-capability single-invocation proof.

REQUIRED SCRUTINY
Trace a process death after begin_capability_execution is durably checkpointed but before record_capability_result. Determine whether pathless resume can safely distinguish zero effect, completed effect, and unknown effect without replay. Check whether caller-provided operation, target, or evidence can select authority not fully determined by the canonical grant. Check for any reachable direct request/result injection, pre-authorization observation, web/network path, negative-verdict evidence bypass, or steward acceptance bypass. Compare the implementation to the active goal's interruption, contradiction, typed proof, dispatcher-only mutation, and distinct-principal requirements; do not treat passing tests as proof of unexercised behavior.

CONSTRAINTS
Review only. Do not modify, execute, publish, merge, or message anyone. Do not claim tests were run. Base every finding on exact packet source with file/symbol citations. Preserve the no-merge boundary and all protected state.

OUTPUT CONTRACT
Return the complete outsource-relay@1 envelope defined in HANDOFF.md with based_on_commit set to {packet_commit} and status PARTIAL unless genuinely BLOCKED or QUESTION. Put severity-ordered findings and the GO/NO-GO verdict in work_product, map findings to the active DCT and single-invocation requirements in evidence, and name one smallest test-first next patch if NO-GO. For transport fidelity, wrap the ENTIRE envelope in exactly one fenced code block labelled text, with no prose before or after it and no nested code fences.
```
