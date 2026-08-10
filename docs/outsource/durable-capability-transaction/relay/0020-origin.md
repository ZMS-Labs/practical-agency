schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0020
stage: 10-host-member-implementation
prepared_utc: 2026-08-10T11:32:51Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: b1104b95-e38e-4e69-b767-6c8df87b9ba6
submission_policy: one prompt-only submission; no attachments; production-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=b1104b95-e38e-4e69-b767-6c8df87b9ba6]

ROLE
Act as the implementation author for Practical Agency's repository-side host-attested member-capability transaction.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 10 only. Read the exact Stage 9 test, Stage 8 architecture relay, current controller, state machine, capability/grant contracts, validation, and orphan recovery. Return the smallest production-only unified diff that makes the committed host-member vertical slice GREEN while preserving all prior focused behavior.

VERIFIED RED
The origin ran the exact Stage 9 test once. The absent-registry subtest failed because caller-free issue raised TypeError for the five old required selection arguments instead of ControllerError(HOST_CAPABILITY_REGISTRY_UNAVAILABLE). The host-member subtest failed because ManifestController rejected the reserved host_capability_registry dependency. No other failure occurred before those boundaries.

CONSTRAINTS
Implement only the repository consumer side with a fail-closed absent default and the fake reserved protocol seam. Do not invent a real Codex adapter, accept caller roots/handles/results, alter tests, enable web, integrate whole-mission proof, change principal handling, add shell/mutation, execute, publish, merge, message anyone, or claim tests were run. Preserve compatibility only where existing tests require it. The patch must apply directly to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the production-only unified diff in work_product, map requirements to hunks in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
