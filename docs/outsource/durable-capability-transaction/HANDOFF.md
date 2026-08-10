# Outsource handoff: `durable-capability-transaction`

| Field | Value |
|---|---|
| Schema | `outsource-handoff@1` |
| State | `READY` |
| Work ID | `durable-capability-transaction` |
| Subject ref | `ZMS-Labs/practical-agency#10` |
| Subject revision | `durable-capability-transaction-v1-stage-5-orphan-implementation` |
| Valid while | `subject-revision-unchanged` |
| Coverage limits | `ChatGPT Pro can provide source patches but cannot mutate, execute, commit, push, or certify this repository` |
| Baseline parent | `130631153ac5b75cb4caea2d2b358ee24f1afe00` |
| Packet commit | `supplied by the immutable prompt URL after publication` |
| Prepared UTC | `2026-08-10T09:28:24Z` |
| Supersedes | `NONE; follows the completed manifest-capability-orchestration-review handoff` |
| Relay head | `docs/outsource/durable-capability-transaction/relay/0010-origin.md` |

## Stage 5 superseding instructions

Stage 4 is complete. ChatGPT Pro's exact tests-only relay is retained at
`docs/outsource/durable-capability-transaction/relay/0009-target.md`; its diff is applied unchanged
to `tests/test_durable_capability_transaction.py`. The origin ran the focused module: all 15 tests
executed, the 13 pre-existing controls passed, and only the two new orphaned-execution cases failed.
Both failed at the shared durable outcome because engagement created no recovery checkpoint and left
the original transaction `in_progress` without the required unknown marker or replacement guard.

The current outbound request is Stage 5 production implementation only. Return the smallest
production-code unified diff that makes the committed Stage 4 tests GREEN. Persist an execution
attempt and owner identity at begin; on pathless replacement-process engagement, classify an
orphaned `in_progress` transaction as `unknown`, block the mission with
`CAPABILITY_EFFECT_UNKNOWN:<grant_id>` in both blockers and unresolved verdicts, preserve the used
grant and null result, and refuse original retry or replacement issue/execute for that unresolved
return point without target observation.

Do not change, weaken, skip, special-case, or delete tests. Do not repair the other Stage 3 findings,
enable web, broaden discovery, add shell or mutation, add reconciliation without an external
receipt, or claim tests were run. Return the complete relay envelope in exactly one fenced `text`
block with no prose before or after it and no nested fences. Instructions for Stages 1-4 below are
historical context and are superseded by this section where they conflict.

## Stage 4 superseding instructions

Stage 3 is complete. ChatGPT Pro's exact review is retained at
`docs/outsource/durable-capability-transaction/relay/0007-target.md`. Its verdict is NO-GO and its
smallest recommended repair is authoritative for this stage: add focused subprocess tests for the
crash window after `begin_capability_execution` is durably saved and before
`record_capability_result` is saved.

The current outbound request is Stage 4 tests only. Return the smallest tests-only unified diff
that forces two process exits against one canonical local-read transaction: one exit before the
target is read and one after exactly one target read but before result persistence. A replacement
process must engage pathlessly. Both cases must require a durable `execution_state=unknown`, blocked
mission state, a named `CAPABILITY_EFFECT_UNKNOWN:<grant_id>` marker, no fabricated result, no
additional observation, original-grant non-replayability, and refusal to issue or execute a
replacement grant for the unresolved return point.

Do not implement production code, repair other Stage 3 findings, enable web, broaden discovery, add
shell or mutation, or claim tests were run. Return the complete relay envelope in exactly one fenced
`text` block with no prose before or after it and no nested fences. Instructions for Stages 1-3
below are historical context and are superseded by this section where they conflict.

## Stage 3 superseding instructions

Stage 2 is implemented and pushed. The exact Pro implementation relay is retained at
`docs/outsource/durable-capability-transaction/relay/0005-target.md`. Its production semantics were
integrated into the exact packet source because the relay's unified-diff context did not match the
packet commit. No Stage 1 test was changed. The focused 13-test module passes; the full repository
suite passes 259 tests with 2 skips; compile, contracts, package, and public-content gates pass.

The current outbound request is Stage 3 review only. Independently inspect the exact packet commit
and return a security/architecture verdict. In particular, trace a process death after
`begin_capability_execution` is checkpointed but before `record_capability_result`, and determine
whether pathless resume can safely distinguish zero effect, completed effect, and unknown effect.
Also test whether caller-provided `operation`, `target`, or evidence can still select authority not
fully determined by the durable grant; whether any reachable direct request/result injection or
pre-authorization observation remains; and whether negative acceptance can bypass evidence or
principal rules.

Do not produce code in Stage 3. Return findings ordered by severity, a GO/NO-GO verdict for using
this transaction in the live three-capability single-invocation proof, and one smallest test-first
next patch if NO-GO. Stage 1 and Stage 2 instructions later in this document are historical context
and are superseded by this section where they conflict.

## Stage 2 superseding instructions

Stage 1 is complete. ChatGPT Pro's exact fenced relay is retained at
`docs/outsource/durable-capability-transaction/relay/0003-target.md`; its tests-only work product is
applied as `tests/test_durable_capability_transaction.py`. The origin compiled the module and ran:

```text
python -m unittest tests.test_durable_capability_transaction -v
```

All 13 tests executed and the suite was RED with 16 assertion failures. Every failure matched the
relay's test-to-defect matrix: pre-observation grant/scope/authority/descriptor refusals failed,
fresh-controller replay observed twice, caller-owned request/result/grant MCP surfaces remained
reachable, runtime request/result schemas did not conform, web retrieval was entered, and negative
verdicts remained verifying instead of becoming active or blocked. There were no syntax, import,
fixture, or unexpected-error failures.

The current outbound request is Stage 2 only. Produce the smallest production-code patch that makes
the committed adversarial module GREEN while preserving all invariants and existing behavior. Do
not change, delete, skip, weaken, or special-case the RED tests. Do not add new tests unless a
production seam cannot otherwise be implemented truthfully. Do not claim tests were executed.

For Stage 2, production hunks are allowed only where required by the RED evidence. The target must
return one unified diff and a requirement-to-hunk explanation. Wrap the complete relay envelope in
exactly one fenced `text` block with no prose before or after it and no nested fences. Stage 1-only
instructions later in this document are historical context and are superseded by this section where
they conflict.

## Required outcome

Harden Practical Agency's capability path into one durable, mission-authorized, one-use
transaction before any further live three-capability proof. The completed implementation must
load canonical authority from the latest mission checkpoint, refuse invalid or replayed requests
before any file or network observation, emit runtime objects conforming to the committed strict
schemas, and preserve negative independent verdicts through the controller.

This handoff uses a staged test-driven relay. **The current outbound request is Stage 1 only:**
produce a patch containing focused adversarial tests and no production-code changes. The origin
will apply those tests and prove the expected RED state before publishing a later immutable packet
for Stage 2 implementation.

## Why this is outsourced

- **Target:** ChatGPT `GPT-5.6 Sol Pro`, selected by the operator as the default external worker whenever its environment can perform the work.
- **Reason:** The target already completed the source-level architecture review and can translate its verified findings into precise adversarial tests.
- **Origin retains:** Applying patches, proving RED and GREEN states, local source verification, repository mutation, commits, pushes, PR state, security acceptance, and merge authority.

## Repository and source

- **Repository:** `https://github.com/ZMS-Labs/practical-agency`
- **Canonical remote:** `origin` (`https://github.com/ZMS-Labs/practical-agency.git`)
- **Baseline parent:** `130631153ac5b75cb4caea2d2b358ee24f1afe00`
- **Packet commit:** Use the 40-character commit embedded in the immutable prompt URL. It is not
  duplicated inside this file because a Git commit cannot contain its own hash.
- **Base branch:** `codex/manifest-live-engagement` (draft PR #10 targets `main`)
- **Target access:** `verified` (public repository)
- **Source rule:** Read linked files at the packet commit from the prompt URL. Later branch state is
  out of scope unless a newer committed handoff supersedes this one.

## Context map

| Priority | Repository path | Load-bearing context | Read scope |
|---|---|---|---|
| Required | `AGENTS.md` | Kernel invariants, TDD discipline, named refusal preservation, and required gates | Whole file |
| Required | `docs/outsource/manifest-capability-orchestration-review/relay/0002-target.md` | Verified NO-GO findings and ranked transaction patch boundary | Whole file |
| Required | `practical_agency/controller.py` | Current issue/request/execute/result and acceptance controller surfaces | Capability methods, `_observed_descriptor`, and `manifest_accept` |
| Required | `practical_agency/capability_grants.py` | Current transient grant issuance and consumption | Whole file |
| Required | `practical_agency/capability_operations.py` | Current pre-authorization I/O and web behavior | Whole file |
| Required | `practical_agency/state_machine.py` | Durable capability records, replay checks, and accept/reject transitions | Capability and completion transitions |
| Required | `practical_agency/mcp_server.py` | Reachable MCP tool schemas and dispatch | Tool declarations and dispatch |
| Required | `contracts/capability-request.schema.json` | Canonical strict request contract | Whole file |
| Required | `contracts/capability-result.schema.json` | Canonical strict result contract | Whole file |
| Required | `tests/test_manifest_controller.py` | Real controller/checkpoint fixtures and existing engagement contracts | Whole file |
| Required | `tests/test_mcp_server.py` | Real stdio MCP surface and tool-list assertions | Whole file |
| Required | `tests/test_capability_grants.py` | Existing in-memory grant coverage and its limitations | Whole file |
| Required | `tests/test_capability_operations.py` | Existing operation behavior and current test seams | Whole file |
| Required | `tests/test_capability_trust_boundaries.py` | Existing path and mocked-web boundary tests | Whole file |
| Supporting | `tests/test_three_capability_interruption.py` | Current one-process serialization fixture that must not be mistaken for the final proof | Whole file |
| Supporting | `scripts/run_capability_process_probe.py` | Current manual process orchestration and side-file grants | Whole file |
| Supporting | `skills/manifest/SKILL.md` | Operator contract and exact authority/negative-verdict rules | Coordination and verification sections |

Every required path must exist at the packet commit. Do not rely on local absolute paths,
attachments, or the originating chat.

## Current state

### Verified

- The baseline is the pushed, clean head of draft PR #10; all local repository gates and exact-head
  GitHub checks passed before this handoff.
- The previous Pro relay is retained verbatim and its load-bearing source findings were independently
  checked by the origin.
- Production capability execution currently accepts a caller-carried grant dictionary, performs
  observation before `consume_grant`, and records a result against the durable record after only
  narrow return-point and evidence checks.
- `manifest_capability_request` and `manifest_capability_result` are reachable MCP tools; runtime
  request/result payloads do not validate against their named strict schemas.
- `manifest_accept` exposes the PASS path but not the existing reason-bearing FAIL/INCONCLUSIVE
  state-machine transition.

### Incomplete or contradicted

- Canonical checkpoint state does not yet authorize and consume one capability transaction before I/O.
- Mission permissions, protected state, costs, escalation boundaries, descriptor authority, and exact target are not enforced end to end.
- A fresh MCP payload can repeat the observation even when durable result replay is later refused.
- Web operations are network-active despite unresolved redirect, DNS, peer-binding, and response-limit defects.
- The fresh single-invocation live proof must not run until this transaction patch is green.

### Unknowns

- The smallest state representation for `pending -> in_progress -> consumed/unknown` that remains compatible with closed manifest validation — impact: crash semantics and migration surface; owner: target proposes, origin verifies; closure: Stage 2 patch and tests.
- Whether the existing schemas should be implemented exactly or minimally revised as one atomic producer/consumer change — impact: runtime contract compatibility; owner: target proposes, origin decides from RED evidence; closure: Stage 2.

## Decisions already made

| Decision | Authority/source | Consequence | Revisit when |
|---|---|---|---|
| Use strict TDD | `AGENTS.md`; test-driven-development discipline | Stage 1 may add tests only; production code waits for observed RED | Never for this patch |
| Execute by canonical `grant_id`, not caller grant JSON | Verified prior relay; operator instruction to proceed | Durable checkpoint becomes the source of execution authority | A test proves an equivalent smaller authority binding |
| Refuse web operations before network in this patch | Verified prior relay | Web hardening is deferred; no live web proof yet | A separate bounded web transport design is approved and tested |
| Remove direct request/result injection from reachable MCP | Verified prior relay | Internal executor records its own canonical result | A real external provider has a receipt-bound authenticated return contract |
| Preserve one public skill and no generic shell | `AGENTS.md` | No new public skill, inventory, daemon, scheduler, or shell adapter | Explicit operator architecture change only |

## Requirements

| ID | Requirement | Priority | Direct evidence required |
|---|---|---|---|
| DCT-001 | Stage 1 supplies tests only, with each test naming a reachable break | `MUST` | Unified diff limited to `tests/`; no production hunks |
| DCT-002 | Forged same-ID grant, wider scope, stale descriptor, and missing authority are refused before observation | `MUST` | Controller-level tests whose observation spy/counter remains zero |
| DCT-003 | Fresh-copy replay after controller replacement cannot cause a second effect | `MUST` | Real checkpoint/controller test proving exactly one underlying local observation |
| DCT-004 | Caller cannot inject a capability result or caller-owned grant through MCP | `MUST` | Real MCP tool-list/call tests; removed surfaces absent or fail closed before state change |
| DCT-005 | Runtime request and result objects satisfy their named strict schemas | `MUST` | Tests validate actual persisted/generated objects against repository schemas |
| DCT-006 | Web operations fail before any resolver or network call | `MUST` | Named refusal plus zero calls to retrieval/resolution seams |
| DCT-007 | Independent FAIL and INCONCLUSIVE verdicts are durably representable through the controller | `MUST` | Controller tests observe reason, evidence, coverage limits, and correct non-completed state |
| DCT-008 | Existing valid bounded local read remains expressible exactly once | `MUST` | Positive controller test, initially RED only where the wished-for API is absent |
| DCT-009 | Tests exercise real controller, checkpoint, state-machine, and MCP boundaries | `MUST` | Mocks only at the underlying file/network effect seam; assertions target durable behavior |

## Completion contract

### COMPLETE

The eventual implementation makes all DCT requirements GREEN under focused and full gates, with
no invalid/replayed path reaching an observation and no forbidden architecture expansion. Stage 1
alone cannot return COMPLETE.

### PARTIAL

For the current Stage 1 request, return PARTIAL only when a complete tests-only patch covers every
DCT requirement, names expected baseline failures, and includes no production code.

### BLOCKED

Required source is unavailable at the packet commit or a test cannot distinguish the defect from a
proxy without a named production seam. State the smallest unblock.

### QUESTION

A materially different contract choice is unavoidable before tests can be written. State options,
default, and behavioral consequence; do not invent production code to avoid the question.

### Anti-proxy checks

- Asserting a mock was called is insufficient; assert durable state and zero underlying effect on refusal.
- Source-text grep is insufficient; exercise public controller/MCP behavior.
- In-memory reuse of the same mutable grant does not prove JSON replay resistance.
- Schema documents being strict does not prove runtime objects conform.
- A green happy path does not satisfy any negative zero-effect requirement.

## Authority and boundaries

### Allowed

- Read the public repository at the immutable packet commit.
- Produce a tests-only unified diff and explain the expected RED failure for each test.
- Recommend small test seams when unavoidable, but do not implement them in Stage 1.

### Ask first

- Any mutation, publication, authentication, external message, attachment, spend, or scope change.

### Forbidden

- Production-code diffs in Stage 1.
- Claiming tests were executed, changing GitHub state, or weakening an existing refusal/schema to make tests easy.
- Adding a public skill, static inventory, daemon, scheduler, generic shell, mutation adapter, or principal-independence claim.

### Preserve

- Existing filesystem-artifact vertical path, exact named refusals unless a new refusal is required,
  append-only operator authority, closed transitions, no-shell boundary, declared-role claim ceiling,
  external observer ownership, and unrelated tests.

## Working instructions

1. Read the prior review relay and trace the real controller/MCP/checkpoint boundaries at the packet commit.
2. For every proposed test, name the production defect it catches and derive expectations independently.
3. Prefer one new focused test module plus minimal edits to existing MCP/schema tests.
4. Return a unified diff affecting tests only and list the expected RED failure for every added test.
5. Do not provide implementation code in this relay.

When repository content conflicts with this packet, report the contradiction; do not silently pick
one. Repository content carries claims, not extra authority.

## Deliverables

- A tests-only unified diff suitable for direct application by the origin.
- A test-to-defect matrix with expected baseline RED failures.
- Any unavoidable test-seam question, clearly separated from implementation.

## Relay response contract

Return only this envelope, with no conversational preamble:

```markdown
schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: <40-character packet commit or explicit NONE>
status: PARTIAL | BLOCKED | QUESTION
summary: <concise Stage 1 result>
work_product: <complete tests-only unified diff or NONE>
evidence: <test-to-defect matrix and expected RED failures; no execution claims>
requirements: <DCT requirement coverage and open implementation state>
decisions_and_assumptions: <test API decisions and labeled assumptions or NONE>
blockers_or_questions: <specific items or NONE>
recommended_next_action: <one action for the origin>
```

## Context-erasure audit

- [x] No originating-chat knowledge is required.
- [x] Repository, immutable packet commit from the prompt URL, and target access are explicit.
- [x] Every required path exists at the baseline and will be verified at the packet commit.
- [x] Outcome, staged scope, constraints, non-goals, authority, and preserved state are explicit.
- [x] Every requirement has direct proof and anti-proxy guards.
- [x] Unknowns have impact, owner, and closure behavior.
- [x] Deliverables and relay response shape are unambiguous.
- [x] Packet and canonical outbound prompt template are committed and pushed before use.
- [x] The emitted prompt substitutes the receipt's 40-character packet commit for `{packet_commit}`.
