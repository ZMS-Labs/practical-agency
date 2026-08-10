schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0016
stage: 8-member-capability-boundary-review
prepared_utc: 2026-08-10T10:39:38Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: 50130043-8c63-4c4d-84ca-30bb924c4182
submission_policy: one prompt-only submission; no attachments; review-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=50130043-8c63-4c4d-84ca-30bb924c4182]

ROLE
Act as the independent architecture authority for Practical Agency's production member-capability discovery and invocation boundary.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 8 only. Inspect the exact installed-package metadata and checks, capability discovery, controller, MCP startup, host-evidence binding, coordinator, adapters, strict contracts, manifest skill contract, and preserved Stage 3 review. Decide the smallest truthful architecture that lets a production manifest mission discover and invoke an external/member-owned capability without a static inventory or a second public skill.

REQUIRED DECISIONS
State GO/NO-GO for the current plugin_root/skills plus built-in execute_read architecture. Specify how authoritative external capability roots are observed and bound, how duplicate/stale descriptors fail closed, how a member owns method and typed verdict without arbitrary shell or mutation, how durable grants and return points bind invocation and receipts, and whether selection is caller-provided or derived from the blocker. If the Codex host does not expose enough substrate, state the minimal host integration contract required instead of simulating it.

CONSTRAINTS
Review only. Do not modify, test, execute, publish, merge, or message anyone. Do not address web, whole-mission proof integration, principal authentication, generic sandboxed execution, or the final live proof in this stage. Base findings on exact packet source with file/symbol citations.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Include a decisive architecture and control/data-flow in work_product, source evidence, requirement decisions, trust assumptions, GO/NO-GO, and exactly one smallest test-first vertical slice in recommended_next_action. No prose before or after the fence and no nested fences.
```
