#!/usr/bin/env python3
"""Run the bounded external three-process controller continuity proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from practical_agency.filesystem_artifact import (  # noqa: E402
    FilesystemArtifactAdapter,
    FilesystemArtifactError,
)


HOOK = ROOT / "hooks" / "manifest_hook.py"
ARTIFACT_PATH = "docs/operations/process-proof.txt"
ARTIFACT_BYTES = b"Practical Agency survived process death and repaired observed drift.\n"


class ProofError(RuntimeError):
    """A deterministic proof phase failed."""


class ServerProcess:
    def __init__(self, workspace: Path) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT), environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "practical_agency.mcp_server"],
            cwd=workspace,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.responses: queue.Queue[str] = queue.Queue()
        self.request_id = 0
        assert self.process.stdout is not None
        threading.Thread(
            target=self._read,
            args=(self.process.stdout,),
            daemon=True,
        ).start()

    def _read(self, stream: object) -> None:
        for line in stream:  # type: ignore[union-attr]
            self.responses.put(line)

    def request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        self.request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        try:
            raw = self.responses.get(timeout=5)
        except queue.Empty as error:
            diagnostic = ""
            if self.process.poll() is not None and self.process.stderr is not None:
                diagnostic = self.process.stderr.read()
            raise ProofError(f"MCP_RESPONSE_TIMEOUT:{diagnostic}") from error
        response = json.loads(raw)
        if response.get("id") != self.request_id:
            raise ProofError("MCP_RESPONSE_ID_MISMATCH")
        if "error" in response:
            raise ProofError(str(response["error"]))
        return response["result"]

    def initialize(self) -> str:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "controller-process-proof", "version": "1"},
            },
        )
        return str(result["serverInfo"]["processInstanceId"])

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


class ProofRun:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.hook_subprocess_calls = 0
        self.tool_arguments: list[dict[str, object]] = []
        self.tool_use_sequence = 0

    def _hook(self, event: dict[str, object]) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, str(HOOK)],
            cwd=ROOT,
            input=json.dumps(event),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        self.hook_subprocess_calls += 1
        if completed.returncode != 0:
            raise ProofError(f"HOOK_FAILED:{completed.stderr.strip()}")
        return json.loads(completed.stdout)

    def call(
        self,
        server: ServerProcess,
        phase: str,
        name: str,
        arguments: dict[str, object],
        prompt: str,
    ) -> dict[str, Any]:
        self.tool_use_sequence += 1
        session_id = f"proof-session-{phase}"
        turn_id = f"proof-turn-{self.tool_use_sequence}"
        self._hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.workspace),
                "session_id": session_id,
                "turn_id": turn_id,
                "prompt": prompt,
            }
        )
        self.tool_arguments.append(dict(arguments))
        gated = self._hook(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(self.workspace),
                "session_id": session_id,
                "turn_id": turn_id,
                "tool_name": f"mcp__practical_agency__{name}",
                "tool_use_id": f"proof-tool-{self.tool_use_sequence}",
                "tool_input": arguments,
            }
        )["hookSpecificOutput"]
        if gated.get("permissionDecision") != "allow":
            raise ProofError(f"HOOK_DENIED:{gated.get('permissionDecisionReason')}")
        result = server.request(
            "tools/call",
            {"name": name, "arguments": gated["updatedInput"]},
        )
        return result


def _structured(result: dict[str, Any], *, allow_error: bool = False) -> dict[str, Any]:
    if bool(result.get("isError")) and not allow_error:
        raise ProofError(str(result.get("structuredContent")))
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        raise ProofError("MCP_TOOL_RESULT_INVALID")
    return payload


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _direct_bypass_probe(workspace: Path) -> str:
    bypass_path = "docs/operations/direct-bypass-must-not-exist.txt"
    receipt_root = workspace / "missions" / ".direct-bypass-receipts"
    adapter = FilesystemArtifactAdapter(
        workspace,
        receipt_root=receipt_root,
        allowed_paths=(bypass_path,),
    )
    try:
        adapter.dispatch(
            {
                "schema": "execution-request@1",
                "request_id": "direct-bypass",
                "mission_id": "not-a-mission",
                "mission_revision": 1,
                "capability_id": "filesystem-artifact",
                "requested_permissions": ["repository:write"],
                "requested_effects": [f"relpath:{bypass_path}", "utf8:bypass"],
                "estimated_costs": ["one local artifact write"],
                "action": "write-text",
                "expected_before": {"kind": "absent"},
            }
        )
    except FilesystemArtifactError as error:
        code = str(error).split(":", 1)[0]
    else:
        raise ProofError("DIRECT_ADAPTER_BYPASS_SUCCEEDED")
    if (workspace / bypass_path).exists() or list(receipt_root.glob("*.json")):
        raise ProofError("DIRECT_ADAPTER_BYPASS_MUTATED_STATE")
    return code


def run_proof(workspace: Path) -> dict[str, object]:
    if not workspace.is_dir() or not (workspace / ".git").exists():
        raise ProofError("PROOF_WORKSPACE_INVALID")
    run = ProofRun(workspace)
    process_ids: list[str] = []
    checkpoint_hashes: list[str] = []
    verifier_refs: list[str] = []
    refusal_codes: list[str] = []

    phase_a = ServerProcess(workspace)
    try:
        process_ids.append(phase_a.initialize())
        _structured(
            run.call(
                phase_a,
                "a",
                "manifest_engage",
                {},
                "$manifest prove process continuity",
            )
        )
        defined = _structured(
            run.call(
                phase_a,
                "a",
                "manifest_define",
                {
                    "definition": {
                        "instruction": "$manifest prove process continuity",
                        "desired_state": "The governed proof artifact survives process replacement and drift repair.",
                        "governed_artifacts": [
                            {"path": ARTIFACT_PATH, "content": ARTIFACT_BYTES.decode("utf-8")}
                        ],
                        "permissions": ["repository:write"],
                        "protected_state": ["all paths except the governed artifact"],
                        "acceptable_costs": ["one local artifact write"],
                        "escalation_required_for": ["scope expansion"],
                        "stop_conditions": ["receipt verification fails"],
                        "completion_acceptor": "acceptor:operator-review",
                    }
                },
                "$manifest define the process continuity proof",
            )
        )
        contract_hash = str(defined["authority_contract_sha256"])
        _structured(
            run.call(
                phase_a,
                "a",
                "manifest_authorize",
                {"authority_contract_sha256": contract_hash},
                f"approve manifest {contract_hash}",
            )
        )
        dispatched_a = _structured(
            run.call(
                phase_a,
                "a",
                "manifest_dispatch",
                {},
                "continue the manifest mission",
            )
        )
        checkpoint_hashes.append(str(dispatched_a["checkpoint_sha256"]))
        verifier_refs.append(str(dispatched_a["observation"]["result_ref"]))
        mission_id = str(dispatched_a["mission_id"])
    finally:
        phase_a.kill()

    bypass_code = _direct_bypass_probe(workspace)
    refusal_codes.append(bypass_code)
    artifact = workspace / ARTIFACT_PATH
    artifact.write_bytes(b"externally planted drift\n")

    phase_b = ServerProcess(workspace)
    try:
        process_ids.append(phase_b.initialize())
        engaged_b = _structured(
            run.call(
                phase_b,
                "b",
                "manifest_engage",
                {},
                "manifest this",
            )
        )
        drift_reason = str(engaged_b["reason_code"])
        repaired = _structured(
            run.call(
                phase_b,
                "b",
                "manifest_dispatch",
                {},
                "continue the durable mission repair",
            )
        )
        checkpoint_hashes.append(str(repaired["checkpoint_sha256"]))
        verifier_refs.append(str(repaired["observation"]["result_ref"]))
        surviving_receipt = repaired["effect"]
        external_receipt_ref = str(surviving_receipt["external_receipt_ref"])
    finally:
        phase_b.kill()

    if artifact.read_bytes() != ARTIFACT_BYTES:
        raise ProofError("BROKERED_REPAIR_BYTES_MISMATCH")

    phase_c = ServerProcess(workspace)
    try:
        process_ids.append(phase_c.initialize())
        _structured(
            run.call(
                phase_c,
                "c",
                "manifest_engage",
                {},
                "manifest this",
            )
        )
        verified = _structured(
            run.call(
                phase_c,
                "c",
                "manifest_verify",
                {},
                "verify the durable manifest mission",
            )
        )
        verifier_refs.extend(
            str(item["result_ref"])
            for item in verified.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("result_ref"), str)
        )
        refused = _structured(
            run.call(
                phase_c,
                "c",
                "manifest_accept",
                {
                    "acceptor_ref": "mission-steward",
                    "verdict": "PASS",
                    "separation_assurance": "declared-role-separation",
                },
                "attempt steward acceptance",
            ),
            allow_error=True,
        )
        if refused.get("code") != "INDEPENDENT_ACCEPTANCE_REQUIRED":
            raise ProofError(f"STEWARD_ACCEPTANCE_NOT_REFUSED:{refused}")
        refusal_codes.append(str(refused["code"]))
        accepted = _structured(
            run.call(
                phase_c,
                "c",
                "manifest_accept",
                {
                    "acceptor_ref": "acceptor:operator-review",
                    "verdict": "PASS",
                    "separation_assurance": "declared-role-separation",
                },
                "accept the verified manifest mission under the declared role",
            )
        )
        checkpoint_hashes.append(str(accepted["checkpoint_sha256"]))
    finally:
        phase_c.kill()

    receipt_path = Path(external_receipt_ref)
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    mission_path_inputs = sum(
        key in {"mission_id", "mission_path"}
        for arguments in run.tool_arguments
        for key in arguments
    )
    workspace_path_inputs = sum(
        key in {"workspace", "workspace_root", "mission_dir"}
        for arguments in run.tool_arguments
        for key in arguments
    )
    return {
        "schema": "controller-process-proof@1",
        "mission_id": mission_id,
        "process_instance_ids": process_ids,
        "mission_path_inputs": mission_path_inputs,
        "workspace_path_inputs": workspace_path_inputs,
        "drift_reason": drift_reason,
        "direct_adapter_bypass": bypass_code,
        "final_status": str(accepted["mission_status"]),
        "acceptance_assurance": str(accepted["separation_assurance"]),
        "checkpoint_hashes": checkpoint_hashes,
        "external_receipt_ref": external_receipt_ref,
        "external_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "receipt_binding": {
            "mission_id": receipt["mission_id"],
            "mission_revision": receipt["mission_revision"],
            "request_id": receipt["request_id"],
        },
        "verifier_result_refs": list(dict.fromkeys(verifier_refs)),
        "refusal_codes": list(dict.fromkeys(refusal_codes)),
        "hook_subprocess_calls": run.hook_subprocess_calls,
        "claim_limits": [
            "host hook coverage is not an OS sandbox",
            "universal non-bypassability is not proven",
            "distinct principal identity is not proven",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_proof(args.workspace.resolve())
        _atomic_write(args.report.resolve(), report)
    except (ProofError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        "controller process proof ok: "
        f"mission={report['mission_id']} processes={len(report['process_instance_ids'])} "
        f"status={report['final_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
