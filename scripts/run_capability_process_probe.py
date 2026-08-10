from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from practical_agency.controller import ManifestController
from practical_agency.host_evidence import write_host_context, write_host_gate
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.mission_repository import discover_active_mission
from practical_agency.state_machine import apply_event_data
from tests.helpers import record_fixture_verifier_result


def refs(workspace: Path, root: Path, operation: str, turn: str, prompt: str = "$manifest probe") -> dict[str, str]:
    context = write_host_context(workspace_root=workspace, prompt=prompt, session_id="process-probe", turn_id=turn, plugin_root=root)
    gate = write_host_gate(context_ref=context.path, tool_name=f"mcp__practical_agency__{operation}", tool_use_id=turn, session_id="process-probe", turn_id=turn, workspace_root=workspace, lock_reason="explicit-manifest-intent", decision="allow-controller", plugin_root=root)
    return {"_host_context_ref": context.path, "_host_gate_ref": gate.path}


def child(root: Path, workspace: Path, phase: str) -> None:
    controller = ManifestController(plugin_root=root)
    definition = {"instruction":"process capability probe","desired_state":"three bounded reads","governed_artifacts":[{"path":"evidence.txt","content":"process-proof"}],"permissions":["repository:read"],"protected_state":["all other paths"],"acceptable_costs":["bounded reads"],"escalation_required_for":["mutation"],"stop_conditions":["revocation"],"completion_acceptor":"reviewer:independent"}
    if phase == "define":
        defined = controller.manifest_define(definition=definition, **refs(workspace, root, "manifest_define", "define"))
        controller.manifest_authorize(authority_contract_sha256=defined["authority_contract_sha256"], **refs(workspace, root, "manifest_authorize", "authorize", f"$manifest approve manifest {defined['authority_contract_sha256']}"))
        return
    index = int(phase.split("-")[1])
    cases = (("file.read","evidence.txt",["evidence.txt"],["evidence.txt"]),("resource.read","evidence.txt",["evidence.txt"],["evidence.txt"]),("web.open","https://example.test/source",["https://example.test/source","source:https://example.test/source"],["source:https://example.test/source"]))
    operation, target, scope, evidence = cases[index]
    if phase.startswith("issue"):
        issued = controller.manifest_capability_issue(capability_id="dynamic-reader", blocking_condition=f"process-{operation}", admitted_operation=operation, evidence_scope=scope, request={"operation":operation}, **refs(workspace, root, "manifest_capability_issue", f"issue-{index}"))
        (workspace / f"grant-{index}.json").write_text(json.dumps(issued["grant"]), encoding="utf-8")
    else:
        grant = json.loads((workspace / f"grant-{index}.json").read_text(encoding="utf-8"))
        controller.manifest_capability_execute(grant=grant, operation=operation, target=target, evidence_refs=evidence, **refs(workspace, root, "manifest_capability_execute", f"execute-{index}"))


if __name__ == "__main__":
    if len(sys.argv) == 4:
        child(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    else:
        with tempfile.TemporaryDirectory(prefix="pa-process-capability-") as temp:
            base = Path(temp); root = base / "runtime"; workspace = base / "workspace"
            shutil.copytree(ROOT / "hooks", root / "hooks"); shutil.copytree(ROOT / "practical_agency", root / "practical_agency", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (root / "skills" / "dynamic-reader").mkdir(parents=True); (root / "skills" / "dynamic-reader" / "SKILL.md").write_text("---\nname: dynamic-reader\ndescription: bounded reads\nmetadata:\n  persistence: session\n---\n", encoding="utf-8")
            workspace.mkdir(); (workspace / ".git").mkdir(); (workspace / "evidence.txt").write_text("process-proof", encoding="utf-8")
            phases = ["define"] + [item for i in range(3) for item in (f"issue-{i}", f"execute-{i}")]
            for phase in phases:
                subprocess.run([sys.executable, __file__, str(root), str(workspace), phase], cwd=ROOT, check=True, env={**__import__('os').environ, "PYTHONPATH": str(ROOT)})
            manifest = discover_active_mission(workspace).manifest
            observed = record_fixture_verifier_result(manifest, proof_ref="file:evidence.txt", subject_ref="file:evidence.txt", value="capability-result")
            store = FileCheckpointStore(workspace / "missions" / observed.mission_id / "checkpoints")
            store.save(observed)
            verifying = apply_event_data(observed, "begin_verification", "mission-steward", {})
            store.save(verifying)
            completed = apply_event_data(verifying, "accept", "reviewer:independent", {"verdict":"PASS", "evidence_refs":["file:evidence.txt"], "coverage_limits":["process fixture only"], "separation_assurance":"declared-role-separation"})
            store.save(completed)
            print(json.dumps({"status":"PASS","processes":len(phases),"capability_classes":3,"final_status":completed.state["status"],"checkpoints":len(list((workspace / "missions").rglob("*.json")))}))
