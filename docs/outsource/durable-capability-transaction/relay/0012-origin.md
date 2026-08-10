schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0012
stage: 6-positive-mcp-tests
prepared_utc: 2026-08-10T10:01:23Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 089e9093-5e83-48d8-bfca-9e6b63236ecd
submission_policy: one prompt-only submission; no attachments; tests-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=089e9093-5e83-48d8-bfca-9e6b63236ecd]

ROLE
Act as the test author for Practical Agency's positive durable capability transaction over its real stdio MCP surface.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 6 only. Read the Stage 3 review finding about the nested MCP validator, the exact MCP schemas/dispatcher, host-evidence tests, copied-runtime fixtures, strict capability contracts, and current focused tests. Return the smallest tests-only unified diff that proves a valid issue/execute round trip can traverse actual stdio MCP and that malformed nested payloads remain fail-closed.

REQUIRED TEST EVIDENCE
Use real MCP initialize/list/call messages and a copied exact runtime with an eligible dynamically discovered read-only capability. Successfully issue and execute one file.read through MCP, prove one underlying target observation, and validate the persisted canonical request/result against the strict repository schemas. Add negative nested-field cases whose protocol refusal leaves checkpoint identity and observation count unchanged. Do not proxy this with direct controller calls or source-text assertions.

CONSTRAINTS
Tests only. Do not modify production, enable web, broaden production discovery, integrate mission proof, alter principal handling, add shell/mutation, execute, publish, merge, message anyone, or claim tests were run. The patch must apply directly to the exact packet source.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the tests-only unified diff in work_product, include a test-to-defect matrix and expected RED failures in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
