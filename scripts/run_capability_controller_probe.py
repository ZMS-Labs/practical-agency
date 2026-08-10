from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from practical_agency.controller import ManifestController
from practical_agency.host_evidence import write_host_context, write_host_gate


def refs(workspace: Path, root: Path, operation: str, turn: str, prompt: str = "$manifest probe") -> dict[str, str]:
    context = write_host_context(workspace_root=workspace, prompt=prompt, session_id="probe", turn_id=turn, plugin_root=root)
    gate = write_host_gate(context_ref=context.path, tool_name=f"mcp__practical_agency__{operation}", tool_use_id=turn, session_id="probe", turn_id=turn, workspace_root=workspace, lock_reason="explicit-manifest-intent", decision="allow-controller", plugin_root=root)
    return {"_host_context_ref": context.path, "_host_gate_ref": gate.path}


with tempfile.TemporaryDirectory(prefix="pa-capability-live-") as temp:
    root = Path(temp) / "runtime"
    shutil.copytree(ROOT / "hooks", root / "hooks")
    shutil.copytree(ROOT / "practical_agency", root / "practical_agency", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "skills" / "dynamic-reader").mkdir(parents=True)
    (root / "skills" / "dynamic-reader" / "SKILL.md").write_text("---\nname: dynamic-reader\ndescription: bounded reads\nmetadata:\n  persistence: session\n---\n", encoding="utf-8")
    workspace = Path(temp) / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / "evidence.txt").write_text("probe", encoding="utf-8")
    controller = ManifestController(plugin_root=root)
    definition = {"instruction":"probe mission","desired_state":"read evidence","governed_artifacts":[{"path":"evidence.txt","content":"probe"}],"permissions":["repository:read"],"protected_state":["all other paths"],"acceptable_costs":["bounded reads"],"escalation_required_for":["mutation"],"stop_conditions":["revocation"],"completion_acceptor":"reviewer:independent"}
    defined = controller.manifest_define(definition=definition, **refs(workspace, root, "manifest_define", "define"))
    controller.manifest_authorize(authority_contract_sha256=defined["authority_contract_sha256"], **refs(workspace, root, "manifest_authorize", "authorize", f"$manifest approve manifest {defined['authority_contract_sha256']}"))
    results = []
    for index, (operation, target, scope, evidence) in enumerate((("file.read","evidence.txt",["evidence.txt"],["evidence.txt"]),("resource.read","evidence.txt",["evidence.txt"],["evidence.txt"]),("web.open","https://example.test/source",["https://example.test/source","source:https://example.test/source"],["source:https://example.test/source"]))):
        controller = ManifestController(plugin_root=root)
        issued = controller.manifest_capability_issue(capability_id="dynamic-reader", blocking_condition=f"probe-{operation}", admitted_operation=operation, evidence_scope=scope, request={"operation":operation}, **refs(workspace, root, "manifest_capability_issue", f"issue-{index}"))
        controller = ManifestController(plugin_root=root)
        executed = controller.manifest_capability_execute(grant=issued["grant"], operation=operation, target=target, evidence_refs=evidence, **refs(workspace, root, "manifest_capability_execute", f"execute-{index}"))
        results.append(executed["result"]["verdict"])
    print(json.dumps({"status":"PASS","capability_classes":3,"results":results,"mission_checkpoint_count":len(list((workspace / "missions").rglob("*.json")))}))
