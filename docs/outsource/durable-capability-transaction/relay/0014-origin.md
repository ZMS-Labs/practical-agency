schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0014
stage: 7-positive-mcp-implementation
prepared_utc: 2026-08-10T10:26:40Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 9883df05-948a-4cbf-bcb7-006c498bcf27
submission_policy: one prompt-only submission; no attachments; production-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=9883df05-948a-4cbf-bcb7-006c498bcf27]

ROLE
Act as the implementation author for Practical Agency's closed positive durable capability transaction over real stdio MCP.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 7 only. Read the committed Stage 6 test, exact MCP tool schemas, custom validator, controller contracts, and preserved Stage 3 finding. Return the smallest production-only unified diff that admits the valid nested issue/execute frames while retaining protocol-level closure for malformed nested fields.

VERIFIED RED
The origin ran the committed real-stdio test. It executed normally and failed only because request id 103, the otherwise valid manifest_capability_issue frame, returned top-level MCP_PROTOCOL_ERROR. The earlier malformed nested request refusal passed before that point.

CONSTRAINTS
Do not modify tests. Do not make nested objects generically open or defer malformed-shape rejection to the controller. Do not broaden discovery, enable web, integrate mission proof, alter principal handling or orphan recovery, add shell/mutation, execute, publish, merge, message anyone, or claim tests were run. The patch must apply directly to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the production-only unified diff in work_product, map requirements to hunks in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
