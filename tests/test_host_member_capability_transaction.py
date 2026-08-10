from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import practical_agency.controller as controller_module
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.controller import ControllerError, ManifestController
from practical_agency.host_evidence import HostBinding
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_repository import discover_active_mission
from tests import test_durable_capability_transaction as dct_tests


REQUEST_CONTRACT = "contracts/capability-request.schema.json"
RESULT_CONTRACT = "contracts/capability-result.schema.json"
MEMBER_COVERAGE = [
    "bounded external member inspection only",
    "no workspace bytes were observed or mutated",
]


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def host_binding(value: HostBinding) -> dict[str, str]:
    return {
        "session_id": value.context.session_id,
        "turn_id": value.context.turn_id,
        "workspace_root": str(value.workspace_root),
        "context_nonce_sha256": sha(value.context.context_nonce.encode()),
    }


class FakeHostRegistry:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = deepcopy(entry)
        self.catalogs: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []
        self.lookups: list[str] = []
        self.receipts: dict[str, dict[str, Any]] = {}
        self.result_bytes: bytes | None = None

    def observe_member_capabilities(
        self, binding: HostBinding
    ) -> dict[str, Any]:
        body = {
            "schema": "host-capability-catalog@1",
            "observation_id": f"catalog-{len(self.catalogs) + 1}",
            "host_binding": host_binding(binding),
            "entries": [deepcopy(self.entry)],
        }
        result = {**body, "catalog_sha256": sha(canonical(body))}
        self.catalogs.append(deepcopy(result))
        return deepcopy(result)

    def invoke_member_capability(
        self,
        binding: HostBinding,
        invocation_ref: str,
        grant_id: str,
        execution_attempt_id: str,
        canonical_request_bytes: bytes,
    ) -> dict[str, Any]:
        member = self.entry["member_binding"]
        if invocation_ref != member["invocation_ref"]:
            raise AssertionError("unregistered invocation_ref")
        request = json.loads(canonical_request_bytes)
        result = {
            "schema": "capability-result@1",
            "request_id": request["request_id"],
            "status": "completed",
            "verdict": "FAIL",
            "artifact_refs": ["member-result:external-inspector:fail"],
            "observed_effects": [],
            "returned_control_point": deepcopy(request["return_point"]),
            "coverage_limits": deepcopy(MEMBER_COVERAGE),
        }
        self.result_bytes = canonical(result)
        receipt = {
            "schema": "host-capability-invocation-receipt@1",
            "host_binding": host_binding(binding),
            "issue_catalog_sha256": self.catalogs[0]["catalog_sha256"],
            "execute_catalog_sha256": self.catalogs[-1]["catalog_sha256"],
            "member_binding": deepcopy(member),
            "grant_id": grant_id,
            "execution_attempt_id": execution_attempt_id,
            "request_id": request["request_id"],
            "request_sha256": sha(canonical_request_bytes),
            "invocation_status": "completed",
            "result_json": self.result_bytes.decode(),
            "result_sha256": sha(self.result_bytes),
            "returned_control_point": deepcopy(request["return_point"]),
            "external_durable_receipt_ref": (
                f"fake-host-receipt:{execution_attempt_id}"
            ),
            "host_coverage_limits": [
                "fake reserved host broker; no real Codex adapter claim"
            ],
        }
        self.invocations.append(
            {
                "host_binding": host_binding(binding),
                "invocation_ref": invocation_ref,
                "grant_id": grant_id,
                "execution_attempt_id": execution_attempt_id,
                "canonical_request_bytes": canonical_request_bytes,
            }
        )
        self.receipts[execution_attempt_id] = deepcopy(receipt)
        return deepcopy(receipt)

    def lookup_member_invocation(
        self, execution_attempt_id: str
    ) -> dict[str, Any] | None:
        self.lookups.append(execution_attempt_id)
        return deepcopy(self.receipts.get(execution_attempt_id))


class HostMemberCapabilityTransactionRedTest(unittest.TestCase):
    def test_host_member_is_selected_from_durable_blocker_and_receipt_bound(
        self,
    ) -> None:
        fixture = dct_tests.DurableCapabilityTransactionRedTests(
            "test_persisted_request_and_result_cannot_violate_strict_schemas"
        )
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            runtime, workspace, _ = fixture._setup(base)
            shutil.rmtree(runtime / "skills" / "dynamic-reader")
            shutil.copytree(
                dct_tests.ROOT / "contracts",
                runtime / "contracts",
            )

            root = base / "external-member"
            descriptor = (
                root / "skills" / "external-inspector" / "SKILL.md"
            )
            descriptor.parent.mkdir(parents=True)
            shutil.copytree(
                dct_tests.ROOT / "contracts",
                root / "contracts",
            )
            descriptor.write_text(
                "---\nname: external-inspector\n"
                "description: Resolve one typed blocker without mutation.\n"
                "metadata:\n"
                "  kind: skill\n"
                "  persistence: external\n"
                "  independence: actor\n"
                "  authority_required: [repository:read]\n"
                f"  input_contract: {REQUEST_CONTRACT}\n"
                f"  output_contract: {RESULT_CONTRACT}\n"
                "  need_kinds: [bounded-file-observation]\n"
                "  non_mutating: true\n"
                "---\n\n# External inspector\n",
                encoding="utf-8",
            )
            descriptor_bytes = descriptor.read_bytes()
            input_bytes = (root / REQUEST_CONTRACT).read_bytes()
            output_bytes = (root / RESULT_CONTRACT).read_bytes()
            member = {
                "owner_package_id": "fixture.external-member",
                "owner_runtime_sha256": sha(
                    b"\0".join(
                        (
                            descriptor_bytes,
                            input_bytes,
                            output_bytes,
                        )
                    )
                ),
                "capability_id": "external-inspector",
                "descriptor_sha256": sha(descriptor_bytes),
                "input_contract": {
                    "id": REQUEST_CONTRACT,
                    "sha256": sha(input_bytes),
                },
                "output_contract": {
                    "id": RESULT_CONTRACT,
                    "sha256": sha(output_bytes),
                },
                "authority_required": ["repository:read"],
                "need_kinds": ["bounded-file-observation"],
                "non_mutating": True,
                "invocation_ref": "host-invocation:external-inspector:v1",
            }
            entry = {
                "member_root": str(root.resolve()),
                "descriptor_path": "skills/external-inspector/SKILL.md",
                "member_binding": deepcopy(member),
                "availability": "available",
                "degradation_reason": None,
            }
            self.assertNotEqual(root.resolve(), runtime.resolve())

            current = discover_active_mission(workspace)
            payload = current.manifest.to_dict()
            payload["revision"] += 1
            payload["continuity"]["prior_checkpoint"] = str(
                current.receipt.path
            )
            blocker = "inspect the bounded evidence"
            return_point = {
                "mission_id": current.manifest.mission_id,
                "revision": payload["revision"] + 1,
                "frontier_index": 0,
                "label": blocker,
            }
            need = {
                "schema": "capability-need@1",
                "need_id": "need-inspect-bounded-evidence",
                "blocking_condition": blocker,
                "need_kind": "bounded-file-observation",
                "evidence_scope": ["evidence.txt"],
                "required_permissions": ["repository:read"],
                "expected_effects": ["evidence.txt"],
                "estimated_costs": ["bounded reads"],
                "timeout_or_stop_condition": (
                    "return after one bounded member result"
                ),
                "return_point": deepcopy(return_point),
            }
            payload["continuity"]["decisions"].append(
                {
                    "kind": "capability-need",
                    "need": deepcopy(need),
                }
            )
            payload["state"].update(
                status="blocked",
                blockers=[blocker],
                next_action=blocker,
            )
            FileCheckpointStore(
                workspace
                / "missions"
                / current.manifest.mission_id
                / "checkpoints"
            ).save(MissionManifest.from_dict(payload))
            request_schema = json.loads(
                (dct_tests.ROOT / REQUEST_CONTRACT).read_text()
            )
            result_schema = json.loads(
                (dct_tests.ROOT / RESULT_CONTRACT).read_text()
            )

            with self.subTest("absent registry"):
                before = discover_active_mission(workspace)
                refusal: Exception | None = None
                with (
                    fixture._count_reads(
                        workspace / "evidence.txt"
                    ) as reads,
                    patch.object(
                        controller_module,
                        "execute_read",
                        side_effect=AssertionError(
                            "execute_read entered"
                        ),
                    ) as local_read,
                ):
                    try:
                        ManifestController(
                            plugin_root=runtime
                        ).manifest_capability_issue(
                            **fixture._refs(
                                workspace,
                                runtime,
                                "manifest_capability_issue",
                                "registry-missing",
                            )
                        )
                    except (ControllerError, TypeError) as error:
                        refusal = error
                after = discover_active_mission(workspace)
                self.assertEqual(
                    (
                        after.manifest.to_dict(),
                        after.receipt.path,
                        after.receipt.sha256,
                    ),
                    (
                        before.manifest.to_dict(),
                        before.receipt.path,
                        before.receipt.sha256,
                    ),
                )
                self.assertEqual(
                    (reads, local_read.call_count),
                    ([], 0),
                )
                self.assertIsInstance(refusal, ControllerError)
                self.assertEqual(
                    str(refusal),
                    "HOST_CAPABILITY_REGISTRY_UNAVAILABLE",
                )

            with self.subTest("host member"):
                registry = FakeHostRegistry(entry)
                error: Exception | None = None
                grant_id = None
                executed = None
                controller = None
                with (
                    fixture._count_reads(
                        workspace / "evidence.txt"
                    ) as reads,
                    patch.object(
                        controller_module,
                        "execute_read",
                        side_effect=AssertionError(
                            "execute_read entered"
                        ),
                    ) as local_read,
                ):
                    try:
                        controller = ManifestController(
                            plugin_root=runtime,
                            host_capability_registry=registry,
                        )
                        issued = controller.manifest_capability_issue(
                            **fixture._refs(
                                workspace,
                                runtime,
                                "manifest_capability_issue",
                                "member-issue",
                            )
                        )
                        grant_id = fixture._grant_id(issued)
                        executed = (
                            controller.manifest_capability_execute(
                                grant_id=grant_id,
                                **fixture._refs(
                                    workspace,
                                    runtime,
                                    "manifest_capability_execute",
                                    "member-execute",
                                ),
                            )
                        )
                    except (
                        ControllerError,
                        TypeError,
                        AssertionError,
                    ) as caught:
                        error = caught
                self.assertEqual(
                    (reads, local_read.call_count),
                    ([], 0),
                )
                self.assertIsNone(error, str(error))
                self.assertIsInstance(grant_id, str)
                self.assertIsInstance(executed, Mapping)
                assert isinstance(grant_id, str)
                assert isinstance(executed, Mapping)
                assert controller is not None
                self.assertEqual(
                    (
                        len(registry.catalogs),
                        len(registry.invocations),
                        registry.lookups,
                    ),
                    (2, 1, []),
                )

                final = discover_active_mission(workspace)
                record = fixture._record(final.manifest, grant_id)
                grant = record["grant"]
                request = record["request"]
                result = record["result"]
                receipt = record["host_invocation_receipt"]
                attempt = record["execution_attempt_id"]
                request_hash = sha(canonical(request))
                result_hash = sha(canonical(result))
                durable_need = [
                    item["need"]
                    for item in final.manifest.continuity["decisions"]
                    if isinstance(item, Mapping)
                    and item.get("kind") == "capability-need"
                ]
                invocation = registry.invocations[0]
                observed = {
                    "need": durable_need,
                    "grant_need": (
                        grant["need_id"],
                        grant["need_sha256"],
                    ),
                    "grant_member": grant["member_binding"],
                    "grant_catalog_request_return": (
                        grant["issue_catalog_sha256"],
                        grant["request_id"],
                        grant["request_sha256"],
                        grant["return_point"],
                        grant["mutation"],
                    ),
                    "request": (
                        request["mission_id"],
                        request["mission_revision"],
                        request["capability_id"],
                        request["capability_source_sha256"],
                        request["bounded_question_or_action"],
                        request["expected_output_contract"],
                        request["return_point"],
                    ),
                    "attempt": (
                        record["execution_state"],
                        grant["used"],
                        record["execution_owner_id"],
                    ),
                    "invoke": (
                        invocation["invocation_ref"],
                        invocation["grant_id"],
                        invocation["execution_attempt_id"],
                        invocation["canonical_request_bytes"],
                    ),
                    "receipt_member": receipt["member_binding"],
                    "receipt": (
                        receipt["issue_catalog_sha256"],
                        receipt["execute_catalog_sha256"],
                        receipt["grant_id"],
                        receipt["execution_attempt_id"],
                        receipt["request_id"],
                        receipt["request_sha256"],
                        receipt["invocation_status"],
                        receipt["result_sha256"],
                        receipt["returned_control_point"],
                    ),
                    "result": (
                        result["status"],
                        result["verdict"],
                        result["coverage_limits"],
                        canonical(result),
                        result["request_id"],
                        result["returned_control_point"],
                    ),
                }
                expected = {
                    "need": [need],
                    "grant_need": (
                        need["need_id"],
                        sha(canonical(need)),
                    ),
                    "grant_member": member,
                    "grant_catalog_request_return": (
                        registry.catalogs[0]["catalog_sha256"],
                        request["request_id"],
                        request_hash,
                        return_point,
                        False,
                    ),
                    "request": (
                        current.manifest.mission_id,
                        return_point["revision"],
                        member["capability_id"],
                        member["descriptor_sha256"],
                        blocker,
                        member["output_contract"]["id"],
                        return_point,
                    ),
                    "attempt": (
                        "consumed",
                        True,
                        controller.process_instance_id,
                    ),
                    "invoke": (
                        member["invocation_ref"],
                        grant_id,
                        attempt,
                        canonical(request),
                    ),
                    "receipt_member": member,
                    "receipt": (
                        registry.catalogs[0]["catalog_sha256"],
                        registry.catalogs[1]["catalog_sha256"],
                        grant_id,
                        attempt,
                        request["request_id"],
                        request_hash,
                        "completed",
                        result_hash,
                        return_point,
                    ),
                    "result": (
                        "completed",
                        "FAIL",
                        MEMBER_COVERAGE,
                        registry.result_bytes,
                        request["request_id"],
                        return_point,
                    ),
                }
                self.maxDiff = None
                self.assertEqual(observed, expected)
                self.assertEqual(
                    dct_tests._schema_errors(
                        request,
                        request_schema,
                    ),
                    [],
                )
                self.assertEqual(
                    dct_tests._schema_errors(
                        result,
                        result_schema,
                    ),
                    [],
                )
                self.assertEqual(
                    receipt["host_binding"],
                    invocation["host_binding"],
                )
                self.assertEqual(
                    receipt,
                    registry.receipts[attempt],
                )
                self.assertEqual(
                    receipt["result_json"].encode(),
                    registry.result_bytes,
                )
                self.assertIn(
                    receipt["external_durable_receipt_ref"],
                    final.manifest.continuity["durable_artifacts"],
                )
                self.assertEqual(
                    (
                        executed["grant_id"],
                        executed["result"],
                    ),
                    (grant_id, result),
                )
                self.assertEqual(
                    (
                        str(executed["checkpoint_ref"]),
                        executed["checkpoint_sha256"],
                    ),
                    (
                        str(final.receipt.path),
                        final.receipt.sha256,
                    ),
                )
