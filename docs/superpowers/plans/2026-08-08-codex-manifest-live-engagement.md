# Codex-first `manifest` live-engagement implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the proven Practical Agency custody kernel into one installed Codex `manifest` path that creates or resumes a mission without a caller-supplied path, mediates one bounded repository artifact effect, survives controller death, detects planted drift, and reaches honestly labeled acceptance.

**Architecture:** Keep `skills/manifest/SKILL.md` as the sole public skill. Add fixed-schema Codex hooks that create host-observed context and gate receipts, a thin stdio MCP bridge, and a deterministic controller that composes the existing checkpoint store, mission repository, coordinator, `filesystem-artifact@1`, typed verifier, and state machine. Codex owns process lifetime; checkpoints and external receipts own continuity. Unit and process tests prove repository behavior; only an installed fresh-task UAT may prove plugin discovery, trusted hook execution, and covered host-tool denial.

**Tech Stack:** Python 3.12 stdlib, `unittest`, newline-delimited JSON-RPC/MCP over stdio, Codex plugin manifests/hooks, atomic JSON files, SHA-256, existing Practical Agency kernel.

## Global constraints

- Preserve the operator instruction byte-for-byte; authority amendments append.
- Keep exactly one public `SKILL.md`: `skills/manifest/SKILL.md`.
- Expose no generic shell, Python, npm, Git, network, or executable adapter.
- Keep `filesystem-artifact@1` as the only production world-effect adapter.
- Require one-use broker grants and a current host-gate posture before dispatch.
- Treat host hooks as a covered-path guardrail, not a complete same-user security boundary.
- Never infer approval from a role string, tool call, or draft existence.
- Keep `externally-proven` acceptance unavailable until a real principal verifier exists; use `declared-role-separation` otherwise.
- Keep Codex process lifetime host-owned and make correctness independent of reuse or termination.
- Preserve unrelated work and do not add generated `missions/` artifacts to Git.
- Do not install, alter user Codex configuration, push, merge, tag, or publish without the authority required by the active goal.
- Every production behavior follows red -> green -> focused regression -> commit, with DCO trailers.

## File map

Existing kernel to compose, not duplicate:

- `practical_agency/checkpoint_store.py`: atomic checkpoints and drift reopening.
- `practical_agency/mission_repository.py`: unique pathless active-mission discovery.
- `practical_agency/coordinator.py`: authorization, one-use dispatch decisions, broker grants.
- `practical_agency/filesystem_artifact.py`: bounded UTF-8 write and external receipt journal.
- `practical_agency/proof.py`: typed verifier results bound to request, receipt, and observed bytes.
- `practical_agency/state_machine.py`: closed transitions and independent acceptance.
- `practical_agency/manifest_model.py` and `contracts/mission-manifest.schema.json`: closed durable state contract.

New runtime boundary:

- `practical_agency/host_evidence.py`: fixed host-context/gate schemas, atomic storage, binding validation.
- `practical_agency/governed_workspace.py`: governed-path normalization, baselines, and receipt-subtracted drift findings.
- `practical_agency/controller.py`: pathless engage/define/authorize/dispatch/verify/accept operations.
- `practical_agency/mcp_server.py`: stdio JSON-RPC framing and MCP tool exposure only.
- `practical_agency/install_provenance.py`: canonical source/install runtime manifest comparison.
- `hooks/manifest_hook.py` and `hooks/hooks.json`: Codex lifecycle entry points.
- `.codex-plugin/plugin.json`, `.mcp.json`, `.agents/plugins/marketplace.json`: installable local plugin package.

New behavioral tests:

- `tests/test_host_evidence.py`
- `tests/test_manifest_hook.py`
- `tests/test_governed_workspace.py`
- `tests/test_manifest_controller.py`
- `tests/test_mcp_server.py`
- `tests/test_codex_plugin_package.py`
- `tests/test_controller_process_resume.py`
- `tests/test_install_provenance.py`

---

## Task 0: Freeze the already-green custody substrate

**Files:**

- Commit the current goal-related modifications and untracked kernel files.
- Exclude: `missions/e2e-proof-001/` and every generated receipt/checkpoint/artifact.

- [ ] Record `git status --short --branch`, `git diff --stat`, branch, HEAD, and remotes.
- [ ] Run the existing 180-test baseline and the five required repository checks.
- [ ] Stage only the reviewed custody-kernel, tests, docs, and `scripts/run_durable_mission_proof.py` files.
- [ ] Confirm `git diff --cached --check` and inspect `git diff --cached --stat`.
- [ ] Commit with the configured author identity and an automatically generated matching DCO trailer:

```powershell
git commit -s -m "feat: prove durable brokered mission custody"
```

- [ ] Re-run `git status --short` and confirm generated mission evidence remains untracked and unstaged.

## Task 1: Create host-observed context and gate receipts

**Files:**

- Create: `practical_agency/host_evidence.py`
- Create: `hooks/manifest_hook.py`
- Create: `hooks/hooks.json`
- Create: `tests/test_host_evidence.py`
- Create: `tests/test_manifest_hook.py`

**Behavioral break named by the tests:** A model can currently invent a workspace/context path, and no host artifact binds a controller call to the actual prompt, turn, tool-use id, or installed hook bytes.

- [ ] Add tests that invoke the real hook script as a subprocess with literal event fixtures and assert files, JSON output, and refusal codes—not source text.

```python
def test_user_prompt_hook_writes_atomic_context_without_exposing_nonce(self):
    event = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(workspace),
        "session_id": "session-1",
        "turn_id": "turn-1",
        "prompt": "$manifest create the approved runbook",
    }
    completed = run_hook(event)
    self.assertEqual(completed.returncode, 0, completed.stderr)
    receipts = list((workspace / "missions" / ".host-context").rglob("*.json"))
    self.assertEqual(len(receipts), 1)
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    self.assertEqual(payload["schema"], "host-context@1")
    self.assertEqual(payload["prompt"], event["prompt"])
    self.assertEqual(payload["prompt_sha256"], sha256(event["prompt"].encode()).hexdigest())
    self.assertNotIn(payload["context_nonce"], completed.stdout)
```

```python
def test_pre_tool_hook_overwrites_reserved_refs_and_denies_competing_tool(self):
    create_context(workspace, prompt="$manifest do this", session="s", turn="t")
    allowed = run_hook(pre_tool_event("mcp__practical_agency__manifest_engage", {"_host_gate_ref": "forged"}))
    body = json.loads(allowed.stdout)
    updated = body["hookSpecificOutput"]["updatedInput"]
    self.assertNotEqual(updated["_host_gate_ref"], "forged")
    self.assertTrue(Path(updated["_host_gate_ref"]).is_file())

    denied = run_hook(pre_tool_event("shell_command", {"command": "echo bypass"}))
    denial = json.loads(denied.stdout)
    self.assertEqual(denial["hookSpecificOutput"]["permissionDecision"], "deny")
    self.assertEqual(list(workspace.glob("bypass*")), [])
```

- [ ] Run the focused tests and observe `ModuleNotFoundError` / missing hook failures:

```powershell
python -m unittest tests.test_host_evidence tests.test_manifest_hook -v
```

- [ ] Implement closed dataclasses/parsers for `host-context@1` and `host-gate-posture@1` with exact field sets.
- [ ] Resolve the workspace only from the hook event `cwd`; require a `.git` file or directory at that root.
- [ ] Store context at `missions/.host-context/<sha256(session)>/<sha256(turn)>.json` and gate posture at `missions/.host-gates/<sha256(tool_use_id)>.json`.
- [ ] Reject symlinked `missions`, control roots, session directory, receipt path, and any resolved path outside the workspace.
- [ ] Hash the canonical `hooks/hooks.json` plus `hooks/manifest_hook.py` bytes as the hook-definition identity.
- [ ] Generate a fresh 32-byte nonce with `secrets.token_hex(32)` and expose only its SHA-256 through gate posture.
- [ ] Have `PreToolUse` overwrite `_host_context_ref` and `_host_gate_ref`; never preserve caller-supplied reserved values.
- [ ] Create the engagement lock on explicit `$manifest` / `manifest this` intent and retain it while `discover_active_mission()` finds an unfinished mission.
- [ ] Deny shell, `apply_patch`, non-Practical-Agency MCP, and other covered local function tools while locked. Store no tool arguments in denial evidence.
- [ ] Keep the hook write-only to fixed control records; import no coordinator, adapter, controller, or state-transition module.
- [ ] Re-run the focused tests, then the full suite.
- [ ] Commit with DCO: `feat: bind manifest calls to host evidence`.

## Task 2: Add governed-path baselines and expected-before writes

**Files:**

- Create: `practical_agency/governed_workspace.py`
- Modify: `practical_agency/filesystem_artifact.py`
- Modify: `practical_agency/coordinator.py`
- Modify: `practical_agency/state_machine.py`
- Modify: `practical_agency/manifest_model.py`
- Modify: `practical_agency/validation.py`
- Modify: `contracts/mission-manifest.schema.json`
- Modify: `tests/helpers.py`
- Modify existing request/receipt tests as required by the closed schema.
- Create: `tests/test_governed_workspace.py`

**Behavioral break named by the tests:** The current adapter allows a blind overwrite under an allowed prefix, co-locates receipts with its artifact root, and the mission has no durable declaration of exactly which repository files are governed.

- [ ] Add literal path and byte-state tests:

```python
def test_governed_paths_reject_escape_directory_symlink_and_missions_namespace(self):
    for candidate in ("../x", "/absolute", "missions/x", "docs", "link/child.txt"):
        with self.subTest(candidate=candidate):
            with self.assertRaises(GovernedWorkspaceError):
                normalize_governed_paths(workspace, [candidate])

def test_existing_dirty_bytes_are_the_baseline_not_drift(self):
    target.write_bytes(b"operator bytes\n")
    baseline = capture_baseline(workspace, ["docs/alpha.md"])
    self.assertEqual(find_unreceipted_drift(workspace, baseline, []), [])
```

```python
def test_expected_before_mismatch_prevents_receipt_and_artifact_mutation(self):
    target.write_bytes(b"changed elsewhere\n")
    decision = coordinate_expected_write(expected_sha256=sha256(b"old\n").hexdigest())
    with self.assertRaisesRegex(FilesystemArtifactError, "EXPECTED_BEFORE_STATE_MISMATCH"):
        dispatch_once(manifest, decision, adapter)
    self.assertEqual(target.read_bytes(), b"changed elsewhere\n")
    self.assertEqual(list(receipt_root.glob("*.json")), [])
```

- [ ] Run the focused tests and observe missing governed-workspace behavior.
- [ ] Add `continuity.governed_workspace` as a closed `governed-workspace@1` object containing normalized paths and literal baseline entries (`absent` or regular-file size/SHA-256 plus parent component identities).
- [ ] Add a closed `expected_before` object to execution inputs/requests and every request-validation boundary.
- [ ] Change `FilesystemArtifactAdapter` construction to separate `artifact_root` (repository root) from `receipt_root` (mission-owned durable receipts).
- [ ] Refuse absolute paths, traversal, `missions/`, directories, and any symlink at any governed path component.
- [ ] Check expected-before state before receipt preparation or effect; return exactly `EXPECTED_BEFORE_STATE_MISMATCH` without touching receipt or artifact state.
- [ ] Extend committed receipts with exact before and after bindings and keep canonical request hashing unchanged in meaning.
- [ ] Compute receipt-subtracted governed drift. Return a typed finding with `UNRECEIPTED_WORKSPACE_DRIFT` for a live state not explained by the baseline plus committed mission receipts.
- [ ] Preserve the documented claim limit: identical final bytes written by an uncovered process cannot be causally distinguished.
- [ ] Run focused tests, all request/receipt/state tests, and the full suite.
- [ ] Commit with DCO: `feat: bind effects to governed workspace state`.

## Task 3: Implement pathless engagement, definition, and explicit authority

**Files:**

- Create: `practical_agency/controller.py`
- Create: `tests/test_manifest_controller.py`
- Modify: `practical_agency/mission_repository.py` only if a failing controller test exposes a missing terminal/draft discovery rule.

**Behavioral break named by the tests:** The operator-facing path currently requires hand-built manifests or mission directories, and approval is not bound to the host-observed prompt that explicitly approves a specific authority contract.

- [ ] Add controller tests using real host receipts, checkpoint files, and repository bytes:

```python
def test_engage_without_active_mission_returns_definition_contract(self):
    result = controller.manifest_engage(**host_refs)
    self.assertEqual(result["status"], "MISSION_DEFINITION_REQUIRED")
    self.assertEqual(result["required_fields"], [
        "instruction", "desired_state", "governed_artifacts", "permissions",
        "protected_state", "acceptable_costs", "escalation_required_for",
        "stop_conditions", "completion_acceptor",
    ])
    self.assertNotIn("mission_path", result)

def test_define_preserves_verbatim_instruction_and_returns_approval_token(self):
    result = controller.manifest_define(definition=literal_definition, **host_refs)
    loaded = discover_active_mission(workspace).manifest
    self.assertEqual(loaded.authority["instruction"], literal_definition["instruction"])
    self.assertEqual(result["approval_phrase"], f"approve manifest {result['authority_contract_sha256']}")
    self.assertEqual(loaded.state["status"], "draft")
```

```python
def test_authorize_requires_current_prompt_to_contain_exact_contract_token(self):
    with self.assertRaisesRegex(ControllerError, "HOST_CONTEXT_INVALID"):
        controller.manifest_authorize(authority_contract_sha256=contract_hash, **refs_for_prompt("yes"))
    result = controller.manifest_authorize(
        authority_contract_sha256=contract_hash,
        **refs_for_prompt(f"approve manifest {contract_hash}"),
    )
    self.assertEqual(result["mission_status"], "active")
```

- [ ] Run the focused tests and observe the missing controller failure.
- [ ] Implement a `ManifestController` whose public methods accept business inputs plus only the two reserved host references—never workspace or mission identifiers.
- [ ] Validate host context/gate binding before every operation and include a fresh `process_instance_id` generated once at server/controller process start in every result.
- [ ] Derive a storage-safe mission id from the validated context nonce hash; do not accept a model-supplied mission id.
- [ ] Make `manifest_engage` discover exactly one unfinished mission, validate its latest checkpoint, re-observe governed paths, and return draft/active/blocked/verifying status without advancing revision.
- [ ] Return exact existing mission discovery/integrity refusals; list ids only for ambiguity.
- [ ] Make `manifest_define` validate a closed definition. Each governed artifact contains one normalized path and exact UTF-8 intended bytes. Capture the baseline and save revision 1 before authority.
- [ ] Canonically hash the compact authority contract. Return the exact required approval phrase `approve manifest <sha256>`.
- [ ] Make `manifest_authorize` require the current host-observed prompt to contain that exact phrase, re-hash the durable draft contract, apply `approve`, apply the initial mission-OS frontier, and checkpoint each resulting durable revision.
- [ ] Reject stale gate/context receipts, a changed definition hash, inferred approval, a plain actor label, and authorization of a non-draft mission.
- [ ] Run focused tests and the full suite.
- [ ] Commit with DCO: `feat: add pathless manifest engagement`.

## Task 4: Complete brokered dispatch, verification, and honest acceptance

**Files:**

- Modify: `practical_agency/controller.py`
- Modify: `tests/test_manifest_controller.py`
- Modify: `practical_agency/checkpoint_store.py` only if a failing controller reconciliation test exposes a needed public helper.

**Behavioral break named by the tests:** There is no single operator-facing call that derives the approved artifact action from durable mission state, enforces the host lock, stores the external receipt and typed observation, blocks on drift, and progresses to acceptance without CLI choreography.

- [ ] Add real controller lifecycle tests:

```python
def test_dispatch_uses_durable_intended_bytes_and_current_host_gate(self):
    result = controller.manifest_dispatch(**host_refs)
    self.assertEqual(result["effect"]["adapter_ref"], "filesystem-artifact@1")
    self.assertEqual(target.read_bytes(), APPROVED_BYTES)
    self.assertTrue(Path(result["effect"]["external_receipt_ref"]).is_file())
    latest = discover_active_mission(workspace).manifest
    self.assertEqual(latest.continuity["verifier_results"][-1]["status"], "verified")

def test_dispatch_without_current_gate_fails_before_effect(self):
    with self.assertRaisesRegex(ControllerError, "HOST_GATE_UNAVAILABLE"):
        controller.manifest_dispatch(_host_context_ref=context_ref)
    self.assertFalse(target.exists())
```

```python
def test_verify_detects_planted_drift_and_reopens_repair(self):
    controller.manifest_dispatch(**dispatch_refs)
    target.write_bytes(b"planted drift\n")
    result = controller.manifest_verify(**new_host_refs)
    self.assertIn(result["reason_code"], {"UNRECEIPTED_WORKSPACE_DRIFT", "ARTIFACT_HASH_MISMATCH"})
    self.assertEqual(result["mission_status"], "active")
    self.assertIn("repair live state", result["next_action"])

def test_steward_acceptance_fails_and_declared_role_acceptance_is_honest(self):
    with self.assertRaisesRegex(ControllerError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
        controller.manifest_accept(acceptor_ref="mission-steward", verdict="PASS", **host_refs)
    accepted = controller.manifest_accept(
        acceptor_ref="acceptor:operator-review",
        verdict="PASS",
        separation_assurance="declared-role-separation",
        **host_refs,
    )
    self.assertEqual(accepted["mission_status"], "completed")
    self.assertIn("principal separation is not externally proven", accepted["coverage_limits"])
```

- [ ] Observe focused failures before implementation.
- [ ] Make `manifest_dispatch` derive the only pending approved governed artifact from the durable mission; do not accept free-form path or content inputs.
- [ ] Require a current `allow-controller` gate posture and active engagement lock before coordination.
- [ ] Call `coordinate_once` then `dispatch_once`; never expose an adapter-specific MCP tool or direct adapter handle.
- [ ] On completion, apply `record_execution_receipt`, `record_action`, and `record_verifier_result`, saving a checkpoint after each load-bearing revision.
- [ ] On engage/verify, inspect the latest receipt and governed baseline. Apply reconciliation findings and checkpoint before returning a contradiction.
- [ ] Repair only with the exact state-machine remediation action and the already-approved intended bytes.
- [ ] Make `manifest_verify` accept only the fixed `artifact-bindings` profile. Any generic command/profile request returns `SANDBOXED_VERIFIER_UNAVAILABLE` without a revision change.
- [ ] Enter `verifying` only when all governed artifacts have current verified results, no unexplained delta exists, all required proof refs resolve, and no blockers/unresolved verdicts remain.
- [ ] Make `manifest_accept` delegate to the existing state machine. Preserve self-acceptance refusal and reject `externally-proven` via the existing principal-verifier-unavailable path.
- [ ] Return concise typed status: mission/revision, authority scope, frontier, one effect/observation, checkpoint receipt, unresolved verdicts, coverage limits, and process instance.
- [ ] Run focused tests, existing end-to-end/integrity tests, and full suite.
- [ ] Commit with DCO: `feat: drive brokered manifest missions`.

## Task 5: Expose the controller through a real stdio MCP server

**Files:**

- Create: `practical_agency/mcp_server.py`
- Create: `tests/test_mcp_server.py`

**Behavioral break named by the tests:** A skill cannot call the Python controller through Codex until a real child process completes MCP initialization, lists closed tool schemas, dispatches tool calls, and reports structured failures without corrupting stdout.

- [ ] Add a subprocess integration client that writes literal newline-delimited JSON-RPC messages and reads responses with a timeout.

```python
def test_real_stdio_server_initializes_and_lists_only_manifest_operations(self):
    with running_server() as server:
        initialized = server.request(1, "initialize", INITIALIZE_PARAMS)
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "practical-agency")
        listed = server.request(2, "tools/list", {})
        self.assertEqual(
            [tool["name"] for tool in listed["result"]["tools"]],
            ["manifest_engage", "manifest_define", "manifest_authorize",
             "manifest_dispatch", "manifest_verify", "manifest_accept"],
        )

def test_tool_call_returns_named_refusal_without_advancing_checkpoint(self):
    response = server.request(3, "tools/call", {
        "name": "manifest_dispatch",
        "arguments": {},
    })
    self.assertTrue(response["result"]["isError"])
    self.assertEqual(response["result"]["structuredContent"]["code"], "HOST_GATE_UNAVAILABLE")
    self.assertEqual(checkpoint_paths(), [])
```

- [ ] Run the focused test and observe server/module startup failure.
- [ ] Implement only `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`. Unknown/malformed methods return `MCP_PROTOCOL_ERROR`.
- [ ] Keep stdout protocol-only; diagnostics go to stderr.
- [ ] Define closed JSON Schemas for all six tools. Business schemas never require workspace or mission id. Reserved host fields are optional schema properties solely for hook injection.
- [ ] Convert controller refusals to MCP tool errors with `content`, `structuredContent`, and `isError: true`; do not expose Python tracebacks or advance state.
- [ ] Ignore valid notifications without producing response frames.
- [ ] Include process instance id in successful controller results and server info.
- [ ] Run focused tests and full suite.
- [ ] Commit with DCO: `feat: expose manifest controller over stdio mcp`.

## Task 6: Package one exact Codex plugin and prove source/install identity

**Files:**

- Create: `.codex-plugin/plugin.json`
- Create: `.mcp.json`
- Create: `.agents/plugins/marketplace.json`
- Create: `practical_agency/install_provenance.py`
- Create: `scripts/verify_codex_install.py`
- Create: `tests/test_codex_plugin_package.py`
- Create: `tests/test_install_provenance.py`
- Modify: `skills/manifest/SKILL.md`
- Modify: `.github/scripts/check_package.py`
- Modify: `.github/scripts/check_harness_surfaces.py`
- Modify: `tests/test_manifest_skill.py`
- Modify: `tests/test_harness_surfaces.py`

**Behavioral break named by the tests:** Source-tree success currently says nothing about whether Codex can discover the plugin, launch its server from the installed cache, run its hook bytes, or load the one skill that directs calls into the controller.

- [ ] Add package tests that copy the runtime package to a temporary install root and execute it there.

```python
def test_copied_plugin_starts_without_source_working_directory(self):
    installed = copy_runtime_plugin(temp_root)
    completed = run_mcp_initialize(cwd=installed)
    self.assertEqual(completed["result"]["serverInfo"]["name"], "practical-agency")

def test_source_install_manifest_detects_one_changed_hook_byte(self):
    installed = copy_runtime_plugin(temp_root)
    self.assertEqual(compare_runtime_trees(ROOT, installed)["status"], "match")
    (installed / "hooks" / "manifest_hook.py").write_bytes(b"changed\n")
    with self.assertRaisesRegex(InstallProvenanceError, "INSTALL_PROVENANCE_MISMATCH"):
        compare_runtime_trees(ROOT, installed)
```

- [ ] Run focused tests and observe missing package/provenance failures.
- [ ] Add `.codex-plugin/plugin.json` with `skills: "./skills/"`, `mcpServers: "./.mcp.json"`, and `hooks: "./hooks/hooks.json"` plus public metadata.
- [ ] Add `.mcp.json` with `cwd: "."`, `command: "python"`, and `args: ["-m", "practical_agency.mcp_server"]`; include no absolute path or private host detail.
- [ ] Add `.agents/plugins/marketplace.json` with one `practical-agency` URL source of `./`, `AVAILABLE` installation, and `ON_INSTALL` authentication policy.
- [ ] Update the skill so every non-routine engagement calls `manifest_engage` first, uses only Practical Agency MCP operations for governed effects, presents the exact authority token, and reports the guardrail claim ceiling. Keep it the only public skill.
- [ ] Build a canonical runtime manifest over explicit plugin runtime paths (`.codex-plugin`, `.mcp.json`, `.agents/plugins/marketplace.json`, `hooks`, `skills/manifest`, `practical_agency`, and required contracts). Record relative path, byte size, and SHA-256; exclude Git, missions, docs, tests, caches, and generated evidence.
- [ ] Make `scripts/verify_codex_install.py` compare source and installed roots and atomically write `install-provenance@1` only on an exact match.
- [ ] Extend package checks to validate Codex metadata, relative launch paths, six MCP tools by a real initialize/list exchange, exact one-skill count, and public-content path hygiene.
- [ ] Run focused tests, package/harness/public-content checks, and full suite.
- [ ] Commit with DCO: `feat: package manifest as a codex plugin`.

## Task 7: Prove death, pathless resume, drift repair, and third-process verification

**Files:**

- Create: `tests/test_controller_process_resume.py`
- Create: `scripts/run_controller_process_proof.py`
- Modify controller/host/adapter modules only for failures exposed by this process proof.

**Behavioral break named by the test:** In-process lifecycle tests cannot prove that all grants and memory disappear, a replacement process resumes only from checkpoints, or a third process can validate the surviving receipt bindings.

- [ ] Write the real three-process test before the harness implementation. It must launch `python -m practical_agency.mcp_server` separately for each phase and use the real hook subprocess to issue each context/gate pair.
- [ ] Phase A: engage, define, explicitly authorize, dispatch the approved artifact, capture process instance and checkpoint receipt, then terminate the server process without a graceful controller handoff.
- [ ] Outside Codex/controller code, plant authorized test drift by writing different bytes directly to the governed file.
- [ ] Phase B: start a new server with no mission path/id, call engage, assert a different process instance, detect the contradiction, dispatch the durable repair action, and terminate.
- [ ] Phase C: start a third server, call engage/verify, inspect the external receipt and request/mission/revision binding, reject steward acceptance, then accept under the declared acceptor.

```python
self.assertEqual(report["schema"], "controller-process-proof@1")
self.assertEqual(len(set(report["process_instance_ids"])), 3)
self.assertEqual(report["mission_path_inputs"], 0)
self.assertIn(report["drift_reason"], ["UNRECEIPTED_WORKSPACE_DRIFT", "ARTIFACT_HASH_MISMATCH"])
self.assertEqual(report["direct_adapter_bypass"], "BROKER_DISPATCH_REQUIRED")
self.assertEqual(report["final_status"], "completed")
self.assertEqual(report["acceptance_assurance"], "declared-role-separation")
```

- [ ] Observe the process test fail before adding the runner.
- [ ] Implement the smallest deterministic runner. It may orchestrate test processes and plant drift, but it must not add a production shell adapter or claim to be the operator path.
- [ ] Persist `controller-process-proof@1` with process ids, checkpoint hashes, receipt ref/hash, verifier result refs, refusal codes, and claim limits.
- [ ] Assert process B and C derive workspace/mission solely from host evidence and durable discovery.
- [ ] Assert direct adapter dispatch still fails before artifact or receipt mutation.
- [ ] Run the focused process test three times to catch lifecycle flakiness, then the full suite.
- [ ] Commit with DCO: `test: prove controller restart and drift recovery`.

## Task 8: Install and run fresh-task Codex dogfood UAT

**Authority gate:** Stop and request explicit approval immediately before mutating the user's Codex marketplace/plugin configuration. Do not interpret approval of this design or code as approval to install.

**Dogfood governed artifact:** `docs/operations/codex-manifest-alpha.md` with exact bytes included in the mission definition before dispatch.

- [ ] Commit all source work first and record branch, commit, working-tree fingerprint, Codex version, Python version, and exact plugin runtime manifest.
- [ ] After explicit installation approval, add the local marketplace with the observed CLI:

```powershell
codex plugin marketplace add Y:\dev\practical-agency --json
codex plugin list --available --json
codex plugin add practical-agency@practical-agency-dev --json
codex plugin list --json
```

- [ ] Locate the installed cache root from the JSON result; do not guess it. Run `scripts/verify_codex_install.py` against source and cache.
- [ ] Start the installed cache MCP server from its own root and record a real initialize/tools-list exchange.
- [ ] Run a fresh Codex task with `$manifest` and the approved dogfood definition. The operator supplies no mission id/path and invokes no Practical Agency CLI.
- [ ] Attempt shell, `apply_patch`, and a non-Practical-Agency MCP tool while engagement is locked; record host denials before execution.
- [ ] Dispatch the dogfood artifact, checkpoint, and record process instance A.
- [ ] Terminate that MCP process from the external UAT harness, not through a production adapter.
- [ ] Plant the explicitly authorized drift outside Codex/controller and record its before/after hash.
- [ ] Run a second fresh task with `manifest this`; assert pathless discovery, process instance B, drift detection, and brokered repair.
- [ ] Run a third fresh process/task to verify receipt/checkpoint/request/mission/artifact bindings and record declared-role acceptance unless real principal evidence exists.
- [ ] Record literal `/manifest` only as observed, unsupported, or untested.
- [ ] Persist an engagement report with elapsed time, controller calls, operator clarifications/approvals, revisions, resumptions, repeated-instruction count, denials, prevented false completion, drift detections, recovery time, overhead, source/install hashes, and final claim ceiling.
- [ ] Patch only behavior the installed proof exposes. Repeat the relevant red/green cycle and reinstall an exact cache copy after each source change.
- [ ] Do not merge or push without separate authority.

## Task 9: Exact-head completion audit

- [ ] Run all required checks on the exact final tree:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q practical_agency tests
python .github/scripts/check_contracts.py
python .github/scripts/check_package.py
python .github/scripts/check_harness_surfaces.py
python .github/scripts/check_public_content.py
```

- [ ] Run the controller three-process proof and installed-cache initialize/list proof again.
- [ ] Re-run source/install provenance and verify the installed cache matches the exact committed/runtime manifest.
- [ ] Inspect `git diff --check`, `git status --short`, commit DCO trailers, and final diff for accidental second skills, generic execution, daemon claims, private paths, or generated mission evidence.
- [ ] Pressure-test each success criterion against contradictory reachable paths:
  - direct adapter call without grant;
  - stale/model-supplied host refs;
  - competing covered local tool while locked;
  - blind overwrite after planted drift;
  - completion with a string-only proof;
  - steward self-acceptance;
  - unsupported externally-proven principal assurance;
  - source success with an altered installed cache.
- [ ] Commit any verification-exposed fix through its own red/green cycle with DCO.
- [ ] Record final working-tree, local-commit, installed-cache, and pushed states separately.
- [ ] Mark the active goal complete only when the installed fresh-task proof and every success criterion are actually satisfied. Do not merge.

## Plan self-review

- Every approved design responsibility maps to a task and a live or automated oracle.
- Unit tests prove fixed schemas, path safety, controller behavior, protocol behavior, and exact bytes.
- Process tests prove memory/grant loss and durable resumption.
- Installed fresh-task UAT alone proves Codex discovery, current hook execution, and covered host denials.
- No test equates source text with runtime behavior; package metadata is exercised by copying/launching the plugin.
- No placeholder, generic executor, daemon, second public skill, or unsupported principal claim is introduced.
- The remaining unproven boundary—malicious same-user mutation or uncovered hosted/specialized tools—is an explicit coverage limit, not hidden by terminology.
