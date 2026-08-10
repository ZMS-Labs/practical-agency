schema: outsource-relay-origin@1
work_id: durable-capability-transaction
sequence: 0022
stage: 11-host-receipt-reconciliation-tests
prepared_utc: 2026-08-10T12:32:56Z
target: ChatGPT GPT-5.6 Sol Pro
request_id: bcdbe5f5-2087-47da-923a-5f99e6050394
submission_policy: one prompt-only submission; no attachments; tests-only response

## Canonical outbound prompt

```text
[CODEX-CONSULT request_id=bcdbe5f5-2087-47da-923a-5f99e6050394]

ROLE
Act as the test author for Practical Agency's host-owned invocation-receipt reconciliation boundary.

TASK
Read and follow https://github.com/ZMS-Labs/practical-agency/blob/{packet_commit}/docs/outsource/durable-capability-transaction/HANDOFF.md. Complete Stage 11 only. Read the exact current host-member test, controller, state machine, Stage 8 architecture relay, and Stage 10 implementation relay. Return exactly one smallest tests-only unified diff proving that a replacement controller reconciles a completed host-owned receipt after the first controller dies post-invocation but pre-local-result-checkpoint, with no reinvocation.

VERIFIED BASELINE
At exact pushed commit 943e1fde12707da2a12d55e0821385d7e3aa3386, the focused host-member and durable transaction tests pass, the full suite passes 263 tests with 2 skips, all repository gates pass, and PR #10 is open/draft and unmerged. The current controller invokes the host once and validates/persists its receipt on the normal path, but pathless engagement currently marks every foreign in-progress attempt unknown without consulting lookup_member_invocation.

CONSTRAINTS
Tests only. Do not implement production code, alter existing tests, invent a real Codex adapter, accept caller roots/handles/results, enable web, integrate whole-mission proof, change principal handling, add shell/mutation, execute, publish, merge, message anyone, or claim tests were run. Use real replacement-controller engagement and durable checkpoint discovery. Preserve the strict absent/invalid lookup control and exact receipt bindings.

OUTPUT CONTRACT
Return only one fenced text block containing a complete outsource-relay@1 envelope. Put the tests-only unified diff in work_product, name the exact expected RED boundary in evidence, and name one next action for the origin. No prose before or after the fence and no nested fences.
```
