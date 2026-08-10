schema: outsource-relay-origin@1
work_id: manifest-capability-orchestration-review
sequence: 0001
prepared_utc: 2026-08-10T05:06:16Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: c80ae20c-0558-4b41-a433-46030624cc0f
submission_policy: one prompt-only submission; no attachments; no retry without fresh operator approval

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=c80ae20c-0558-4b41-a433-46030624cc0f]

ROLE
Act as an independent adversarial architecture reviewer. You have advisory authority only.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/manifest-capability-orchestration-review/HANDOFF.md. Read the linked repository files at that exact commit and assess the implementation against the packet requirements.

CONTEXT AND EVIDENCE
The durable repository handoff is the complete context. Use no originating-chat assumptions and no attachments.

CONSTRAINTS
Do not modify, publish, merge, or message anyone. Do not claim to have executed tests or runtime probes. Distinguish code evidence, test evidence, live-proof claims, and unknowns. Prefer concrete load-bearing findings over generic advice.

OUTPUT CONTRACT
Return only the outsource-relay@1 envelope defined in HANDOFF.md, with based_on_commit set to {packet_commit}. No conversational preamble or text after the envelope.
```
