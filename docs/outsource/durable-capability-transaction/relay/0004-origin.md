schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0004
stage: 2-implementation
prepared_utc: 2026-08-10T06:59:28Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 49ea921b-515c-4fec-81ab-c779f8d978f2
submission_policy: one prompt-only submission; no attachments; production patch against committed RED tests

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=49ea921b-515c-4fec-81ab-c779f8d978f2]

ROLE
Act as the implementation engineer for the security-sensitive durable capability transaction. You have advisory patch authority only.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 2 only: produce the smallest production-code unified diff that makes the committed tests/test_durable_capability_transaction.py GREEN without weakening it.

CONTEXT AND EVIDENCE
The exact Stage 1 Pro relay, applied RED test module, prior architecture review, and Stage 2 superseding instructions are committed at the packet revision. Use only repository content at that exact commit. The origin observed 13 tests run with 16 expected assertion failures and no syntax, import, fixture, or unexpected-error failures. No attachments.

CONSTRAINTS
Do not modify, execute, publish, merge, or message anyone. Do not claim tests were run. Do not change, delete, skip, weaken, or special-case the RED tests. Preserve one public manifest skill, exact intent and append-only amendments, closed authority transitions, one-use request-bound dispatch grants, no arbitrary shell or generic executable adapter, no daemon or scheduler claims, upstream verifier ownership, public-content and DCO boundaries, unrelated work, and the no-merge boundary. Refuse web transport before resolver or network access in this patch. Remove caller-owned capability request/result/grant injection from reachable MCP. Load and consume canonical durable authority before observation. Preserve reason-bearing FAIL and INCONCLUSIVE results without steward acceptance.

OUTPUT CONTRACT
Return the complete outsource-relay@1 envelope defined in HANDOFF.md with based_on_commit set to {packet_commit} and status PARTIAL unless genuinely BLOCKED or QUESTION. Put the complete production-only unified diff in work_product and map each DCT requirement to its implementing hunks in evidence. For transport fidelity, wrap the ENTIRE envelope in exactly one fenced code block labelled text, with no prose before or after it and no nested code fences.
```
