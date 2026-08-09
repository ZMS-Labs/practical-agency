# Cloud continuation handoff: Codex-first `manifest` live engagement

**Handoff date:** 2026-08-08

**Status:** Active implementation at a verified Task 2 red-test checkpoint

**Repository:** `ZMS-Labs/practical-agency`

**Branch:** `codex/manifest-live-engagement`

**Base:** `origin/main` at `57f37ce39562be13ab59aa0c11d97e26163310f4`

## Operator direction

Continue the existing active goal directly. Do not restart discovery, redesign
the architecture, create a second public skill, or replace the approved proof
oracles with source inspection. Commit and push coherent, DCO-signed
goal-related changes to this branch. Do not merge a pull request.

The objective is to make Practical Agency operator-usable as a Codex-first
`manifest` alpha with pathless create/resume, host-gated and brokered repository
effects, durable receipts and checkpoints, forced interruption, planted-drift
detection and repair, third-process verification, and honestly labeled
acceptance.

Read these files in order before editing:

1. `AGENTS.md`
2. `docs/handoffs/2026-08-08-cloud-manifest-live-engagement.md`
3. `docs/superpowers/specs/2026-08-08-codex-manifest-live-engagement-design.md`
4. `docs/superpowers/plans/2026-08-08-codex-manifest-live-engagement.md`

Use the plan's test-first task order. The approved design is authoritative when
the handoff only summarizes it.

## Durable branch state

The branch tip containing this file is the handoff identity. After fetching,
verify that the checked-out branch tip equals `origin/codex/manifest-live-engagement`
and inspect the commits below it.

Completed commits before the handoff checkpoint:

- `c227872` — design the live manifest engagement
- `f2cc382` — record operator approval of the design
- `4bb72e6` — write the executable TDD implementation plan
- `f6282c8` — prove durable brokered mission custody
- `8555e39` — ignore root mission runtime state
- `2c48770` — bind manifest calls to host evidence

Local `main` was repaired before handoff and exactly matched `origin/main`
with divergence `0/0`. The feature branch differs intentionally because it
contains the unmerged custody substrate and live-engagement work.

## What is already proven

The committed custody kernel provides:

- atomic, hash-bound mission checkpoints;
- pathless discovery of exactly one unfinished mission;
- one-use, process-local broker grants;
- a bounded UTF-8 filesystem artifact adapter with crash-visible receipts;
- typed verifier results bound to mission, revision, request, receipt, and
  observed artifact bytes;
- process death, checkpoint-only resumption, planted-drift detection, brokered
  repair, and third-process verification;
- state-machine refusal of string-only proof, steward self-acceptance, and
  unsupported externally proven principal claims; and
- no generic command dispatch surface.

Task 1 added fixed-schema host evidence and Codex hook behavior:

- `host-context@1` records exact prompt, workspace, session, turn, nonce, and
  installed runtime hash under the mission control namespace;
- `host-gate-posture@1` binds controller permission or covered-tool denial to
  the current context and tool-use identity;
- `PreToolUse` overwrites model-supplied reserved references;
- explicit manifest engagement denies covered shell, patch, non-controller
  MCP, and other local function paths;
- ordinary unlocked turns are not denied; and
- the hook-definition hash covers the imported Python runtime, not only the
  wrapper script.

At the Task 1 checkpoint, the focused tests passed and the full suite reported
187 tests passing with 2 environment-dependent skips. Compile, package, and
public-content checks also passed.

This proves repository behavior only. It does not yet prove that an installed
Codex host accepts or executes the hook definition.

## Exact interruption point: Task 2 red tests

The handoff commit intentionally contains failing tests and no Task 2
production implementation.

Changed tests:

- `tests/test_governed_workspace.py` — new governed-path normalization,
  baseline, receipt-subtracted drift, and manifest round-trip oracles.
- `tests/test_filesystem_artifact_adapter.py` — expected-before refusal and
  separate artifact/receipt root oracles.

The focused command is:

```bash
python -m unittest tests.test_governed_workspace tests.test_filesystem_artifact_adapter.FilesystemArtifactAdapterTests.test_expected_before_mismatch_prevents_receipt_and_artifact_mutation tests.test_filesystem_artifact_adapter.FilesystemArtifactAdapterTests.test_repository_artifact_and_mission_receipt_roots_are_separate -v
```

Expected red failures at handoff:

- `ModuleNotFoundError: No module named 'practical_agency.governed_workspace'`
- `TypeError: FilesystemArtifactAdapter.__init__() got an unexpected keyword argument 'receipt_root'`

If these tests pass immediately after a fresh checkout, first verify that the
branch contains later work rather than treating the unexpected green result as
proof.

## Immediate implementation work

Implement only enough Task 2 behavior to make the red tests pass, then run the
existing adapter, coordinator, state-machine, contract, and full-suite checks.

Required interfaces exposed by the red tests:

```python
normalize_governed_paths(workspace_root, paths) -> tuple[str, ...]
capture_baseline(workspace_root, paths) -> dict[str, object]
find_unreceipted_drift(workspace_root, baseline, execution_receipts) -> list[WorkspaceDriftFinding]
```

`WorkspaceDriftFinding` must expose `path` and `reason_code`, with unexplained
live changes returning `UNRECEIPTED_WORKSPACE_DRIFT`.

`FilesystemArtifactAdapter` must remain backward compatible for existing
kernel tests while adding:

```python
FilesystemArtifactAdapter(
    artifact_root,
    receipt_root=mission_owned_receipt_root,
    allowed_paths=("docs/operations/codex-manifest-alpha.md",),
)
```

An optional closed execution input named `expected_before` accepts either an
absent-state binding or a regular-file SHA-256 binding. A mismatch must raise
`EXPECTED_BEFORE_STATE_MISMATCH` before receipt preparation or artifact
mutation. Committed journals record exact `before` and `after` states.

Add `continuity.governed_workspace` as an optional closed manifest field so
older durable checkpoints remain valid. The Codex controller must always use
the guarded form even though legacy internal tests may omit it.

Do not weaken the existing one-use broker grant or expose an adapter-specific
MCP tool to make these tests pass.

## Cloud-capable completion boundary

The cloud agent may complete implementation-plan Tasks 2 through 7:

- governed workspace and expected-before effects;
- pathless engagement, definition, and explicit authority;
- controller dispatch, verification, repair, and honest acceptance;
- real stdio MCP protocol handling;
- Codex-native package metadata and source/install provenance tooling; and
- the real three-process controller death/resume/drift/third-verifier proof.

The cloud agent may use temporary copied plugin roots and subprocesses to prove
package-relative startup. It must not reinterpret a temporary package copy as
installed-host acceptance.

Commit and push each coherent green task. Preserve exact refusal codes and DCO
trailers. Do not add a daemon, generic executor, container claim, second public
skill, or merge.

## Mandatory return-to-local gate

Tasks 8 and 9 require the original local Codex environment or another
explicitly accepted real host with equivalent plugin and hook support. They are
not satisfied by cloud source tests.

Before claiming the active goal complete, the local continuation must:

1. verify the source revision and installed cache with the provenance tool;
2. install and enable the plugin only with current operator authorization;
3. start the MCP server from the installed cache and complete real
   `initialize` and `tools/list` exchanges;
4. invoke `$manifest` and `manifest this` from fresh Codex tasks without a
   mission id, mission path, or Practical Agency CLI choreography;
5. record current host-context and host-gate evidence;
6. attempt covered shell, `apply_patch`, and non-Practical-Agency MCP calls and
   record pre-execution denials;
7. kill the first controller process, resume from a replacement process, plant
   authorized out-of-band drift, detect it, and repair through the broker;
8. have a third process verify checkpoint, receipt, request, mission, and live
   artifact bindings; and
9. record acceptance as `declared-role-separation` unless real principal
   evidence becomes available.

A cloud agent must stop short of a completion claim if it cannot exercise this
installed-host oracle. Its final handback should name the exact pushed commit,
green checks, remaining local commands, and every observed coverage limit.

## Required checks

Run these after each relevant task and at cloud handback:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
python .github/scripts/check_contracts.py
python .github/scripts/check_package.py
python .github/scripts/check_harness_surfaces.py
python .github/scripts/check_public_content.py
```

Also run the focused process and package-install-copy tests introduced by the
implementation plan. Report skipped checks as skipped; never silently promote
them to proof.

## Sidecar research disposition

`HiAi-gg/agent-plugins-builder` was evaluated read-only at upstream commit
`ceab0099382e92bc60ebe2b04c4115cff2f57550`.

Disposition: adapt selected ideas only. Do not add it as a Practical Agency
runtime, build, packaging, or acceptance dependency. Its useful ideas are a
canonical package model, explicit portable/client-specific classifications,
dry-run generation, and separation of generation from validation. Its current
Codex adapter drops hooks, its validation does not start MCP servers or prove
installed caches, and it supplies no authority, receipt, provenance, or
independent-acceptance boundary. Any executable experiment belongs in a
separate shared-tooling repository with synthetic fixtures, not on this
critical path.

## Cloud-session starting instruction

Use this concise instruction after checking out the branch:

> Read `AGENTS.md`, the cloud handoff, the approved live-engagement design, and
> its implementation plan. Continue the active goal directly from the committed
> Task 2 red tests. Implement the smallest green governed-workspace and
> expected-before slice, then execute Tasks 3 through 7 test-first. Commit and
> push coherent DCO-signed changes to `codex/manifest-live-engagement`. Do not
> merge, install into the operator's local Codex environment, or claim the goal
> complete; return an exact-commit handback for local Tasks 8 and 9.
