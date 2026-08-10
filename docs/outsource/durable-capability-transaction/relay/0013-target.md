schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 2d280f26ffdb23a7681b2809ede6218820d796ec
status: PARTIAL
summary: |
  Stage 6 tests-only patch adds one real stdio MCP integration test over the existing copied-runtime fixture. It requires initialize, tools/list, valid capability issue, and valid file.read execution to cross the JSON-RPC process boundary; validates the persisted canonical request and result against the repository contracts; records exactly one underlying target read; and requires malformed nested request and evidence payloads to remain protocol refusals with unchanged checkpoint identity and observation count.
work_product: |
  diff --git a/tests/test_durable_capability_transaction.py b/tests/test_durable_capability_transaction.py
  --- a/tests/test_durable_capability_transaction.py
  +++ b/tests/test_durable_capability_transaction.py
  @@ -24,5 +24,6 @@
   from practical_agency.manifest_model import MissionManifest
   from practical_agency.mcp_server import McpServer, ProtocolError
   from practical_agency.mission_repository import discover_active_mission
   from practical_agency.state_machine import TransitionError, apply_event_data
  +from tests import test_mcp_server as mcp_process_tests
   from tests.helpers import minimal_payload, record_fixture_verifier_result
  @@ -936,2 +937,208 @@
  -
  +
  +    def test_real_stdio_mcp_issue_execute_round_trip_and_nested_fields_fail_closed(
  +        self,
  +    ) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            base = Path(temp)
  +            runtime, workspace, _ = self._setup(base)
  +            journal = base / "stdio-observations.log"
  +            instrumentation = base / "instrumentation"
  +            instrumentation.mkdir()
  +            (instrumentation / "sitecustomize.py").write_text(
  +                "from pathlib import Path\n"
  +                f"_target=Path({str((workspace / 'evidence.txt').resolve())!r}).resolve()\n"
  +                f"_journal=Path({str(journal)!r})\n"
  +                "_read_text=Path.read_text\n"
  +                "def counted(path,*args,**kwargs):\n"
  +                "    if path.resolve()==_target:\n"
  +                "        with _journal.open('a',encoding='utf-8') as stream:\n"
  +                "            stream.write('read\\n'); stream.flush()\n"
  +                "    return _read_text(path,*args,**kwargs)\n"
  +                "Path.read_text=counted\n",
  +                encoding="utf-8",
  +            )
  +
  +            def checkpoint() -> tuple[str, str, int]:
  +                discovered = discover_active_mission(workspace)
  +                return (
  +                    str(discovered.receipt.path),
  +                    discovered.receipt.sha256,
  +                    discovered.manifest.revision,
  +                )
  +
  +            def call(
  +                server: mcp_process_tests.StdioServer,
  +                request_id: int,
  +                name: str,
  +                arguments: Mapping[str, Any],
  +            ) -> dict[str, object]:
  +                return server.request(
  +                    request_id,
  +                    "tools/call",
  +                    {"name": name, "arguments": dict(arguments)},
  +                )
  +
  +            pythonpath = os.pathsep.join(
  +                [str(instrumentation), os.environ.get("PYTHONPATH", "")]
  +            ).rstrip(os.pathsep)
  +            with (
  +                patch.object(mcp_process_tests, "ROOT", runtime),
  +                patch.dict(os.environ, {"PYTHONPATH": pythonpath}),
  +                mcp_process_tests.StdioServer(workspace) as server,
  +            ):
  +                initialized = server.request(
  +                    100, "initialize", mcp_process_tests.INITIALIZE_PARAMS
  +                )
  +                self.assertEqual(
  +                    initialized["result"]["protocolVersion"], "2025-03-26"
  +                )
  +                server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
  +                listed = server.request(101, "tools/list", {})
  +                tool_names = {tool["name"] for tool in listed["result"]["tools"]}
  +                self.assertTrue(
  +                    {"manifest_capability_issue", "manifest_capability_execute"}
  +                    <= tool_names
  +                )
  +
  +                intent = self._intent("file.read", "evidence.txt")
  +                issue_base = {
  +                    "capability_id": "dynamic-reader",
  +                    "blocking_condition": "inspect the bounded evidence",
  +                    "admitted_operation": "file.read",
  +                    "evidence_scope": ["evidence.txt"],
  +                }
  +                bad_issue_args = {
  +                    **issue_base,
  +                    "request": {**intent, "unexpected_nested_field": "forged"},
  +                    **self._refs(
  +                        workspace,
  +                        runtime,
  +                        "manifest_capability_issue",
  +                        "stdio-invalid-issue",
  +                    ),
  +                }
  +                before_bad_issue = checkpoint()
  +                bad_issue = call(
  +                    server, 102, "manifest_capability_issue", bad_issue_args
  +                )
  +                self.assertEqual(
  +                    bad_issue["error"]["data"]["code"], "MCP_PROTOCOL_ERROR"
  +                )
  +                self.assertEqual(checkpoint(), before_bad_issue)
  +                self.assertEqual(self._read_count(journal), 0)
  +
  +                issued_frame = call(
  +                    server,
  +                    103,
  +                    "manifest_capability_issue",
  +                    {
  +                        **issue_base,
  +                        "request": intent,
  +                        **self._refs(
  +                            workspace,
  +                            runtime,
  +                            "manifest_capability_issue",
  +                            "stdio-valid-issue",
  +                        ),
  +                    },
  +                )
  +                self.assertNotIn("error", issued_frame)
  +                self.assertFalse(issued_frame["result"]["isError"])
  +                issued = issued_frame["result"]["structuredContent"]
  +                grant_id = self._grant_id(issued)
  +                issued_checkpoint = checkpoint()
  +                self.assertEqual(issued["status"], "capability-issued")
  +                self.assertEqual(
  +                    (str(issued["checkpoint_ref"]), issued["checkpoint_sha256"]),
  +                    issued_checkpoint[:2],
  +                )
  +                self.assertNotEqual(issued_checkpoint, before_bad_issue)
  +                self.assertEqual(self._read_count(journal), 0)
  +
  +                execute_base = {
  +                    "grant_id": grant_id,
  +                    "operation": "file.read",
  +                    "target": "evidence.txt",
  +                    "evidence_refs": ["evidence.txt"],
  +                }
  +                bad_execute_args = {
  +                    **execute_base,
  +                    "evidence_payload": {
  +                        "evidence.txt": {"unexpected_nested_field": "forged"}
  +                    },
  +                    **self._refs(
  +                        workspace,
  +                        runtime,
  +                        "manifest_capability_execute",
  +                        "stdio-invalid-execute",
  +                    ),
  +                }
  +                before_bad_execute = checkpoint()
  +                bad_execute = call(
  +                    server, 104, "manifest_capability_execute", bad_execute_args
  +                )
  +                self.assertEqual(
  +                    bad_execute["error"]["data"]["code"], "MCP_PROTOCOL_ERROR"
  +                )
  +                self.assertEqual(checkpoint(), before_bad_execute)
  +                self.assertEqual(self._read_count(journal), 0)
  +
  +                executed_frame = call(
  +                    server,
  +                    105,
  +                    "manifest_capability_execute",
  +                    {
  +                        **execute_base,
  +                        **self._refs(
  +                            workspace,
  +                            runtime,
  +                            "manifest_capability_execute",
  +                            "stdio-valid-execute",
  +                        ),
  +                    },
  +                )
  +                self.assertNotIn("error", executed_frame)
  +                self.assertFalse(executed_frame["result"]["isError"])
  +                executed = executed_frame["result"]["structuredContent"]
  +
  +            discovered = discover_active_mission(workspace)
  +            record = self._record(discovered.manifest, grant_id)
  +            request, result = record.get("request"), record.get("result")
  +            self.assertIsInstance(request, Mapping)
  +            self.assertIsInstance(result, Mapping)
  +            assert isinstance(request, Mapping) and isinstance(result, Mapping)
  +            request_schema = json.loads(
  +                (ROOT / "contracts" / "capability-request.schema.json").read_text()
  +            )
  +            result_schema = json.loads(
  +                (ROOT / "contracts" / "capability-result.schema.json").read_text()
  +            )
  +            self.assertEqual(executed["status"], "capability-executed")
  +            self.assertEqual(executed["grant_id"], grant_id)
  +            self.assertEqual(executed["result"], result)
  +            self.assertEqual(
  +                (str(executed["checkpoint_ref"]), executed["checkpoint_sha256"]),
  +                (str(discovered.receipt.path), discovered.receipt.sha256),
  +            )
  +            self.assertEqual(self._read_count(journal), 1)
  +            self.assertEqual(_schema_errors(request, request_schema), [])
  +            self.assertEqual(_schema_errors(result, result_schema), [])
  +            self.assertEqual(request["capability_id"], "dynamic-reader")
  +            self.assertEqual(
  +                request["expected_output_contract"],
  +                "contracts/capability-result.schema.json",
  +            )
  +            self.assertEqual(result["request_id"], request["request_id"])
  +            self.assertEqual(result["status"], "completed")
  +            self.assertEqual(
  +                result["observed_effects"],
  +                [
  +                    {
  +                        "target": "evidence.txt",
  +                        "content": "authorized evidence",
  +                        "mutation": False,
  +                    }
  +                ],
  +            )
  +
       def test_mcp_tool_list_removes_injection_surfaces_and_caller_grant(self) -> None:
evidence: |
  TEST-TO-DEFECT MATRIX — expected behavior only; no tests were executed here.

  1. test_real_stdio_mcp_issue_execute_round_trip_and_nested_fields_fail_closed — positive issuance:
     Sends actual initialize, notifications/initialized, tools/list, and tools/call frames to python -m practical_agency.mcp_server while the subprocess imports the copied runtime containing dynamic-reader. This catches the Stage 3 impossibility where request is advertised only as {"type":"object"} and _validate rejects every nonempty valid request.

     Expected committed-baseline RED: request id 103 returns a top-level MCP_PROTOCOL_ERROR, so self.assertNotIn("error", issued_frame) fails. The earlier extra-request-field refusal is expected to remain green.

  2. Same test — positive execution and durable canonical contracts:
     After successful MCP issuance, executes the returned canonical grant_id through the same stdio process, reloads the actual checkpoint, and validates the persisted request and result with _schema_errors against contracts/capability-request.schema.json and contracts/capability-result.schema.json. It also binds the response checkpoint path and digest to the latest durable receipt.

     Expected committed-baseline state: these assertions are not reached until the valid nested request can traverse the MCP validator. They become regression evidence for the production repair rather than a direct-controller proxy.

  3. Same test — one underlying observation:
     An external test-only sitecustomize seam wraps Path.read_text only in the MCP subprocess and journals access only when the exact workspace evidence.txt target is read. The malformed calls require zero journal entries; the successful execution requires exactly one entry and the persisted observed effect must contain the target's exact bytes.

  4. Same test — malformed nested request:
     Adds unexpected_nested_field inside the otherwise valid request object. It must produce a protocol-level MCP_PROTOCOL_ERROR, preserve checkpoint path/digest/revision, and leave the observation journal at zero. This prevents repairing the positive path by making request an unrestricted open object or by deferring rejection to the controller.

  5. Same test — malformed nested evidence:
     Supplies an object-valued nested evidence_payload member before valid execution. It must produce a protocol-level MCP_PROTOCOL_ERROR with the issued checkpoint identity and zero-read count unchanged. This catches an overbroad validator repair that would admit arbitrary nested evidence and allow the file operation to proceed before refusal.
requirements: |
  - Stage 6 tests-only boundary: satisfied; the diff changes only tests/test_durable_capability_transaction.py.
  - DCT-004 / real MCP boundary: initialize, tools/list, and tools/call traverse the real newline-delimited stdio process; malformed nested fields require protocol refusal.
  - DCT-005 / strict runtime objects: the actual persisted canonical request and result are checked against the committed repository schemas and cross-bound by request_id and checkpoint receipt.
  - DCT-008 / bounded positive local read: one dynamically discovered dynamic-reader grant must issue and execute one file.read through MCP.
  - DCT-009 / anti-proxy evidence: the test uses copied runtime bytes, real host context/gate receipts, the real checkpoint store, real subprocess stdio, and an underlying read counter; it invokes no controller method directly.
  - Open implementation state: the valid request remains expected RED until production supplies an MCP nested request schema and validator behavior that admit exactly the controller's valid intent while retaining protocol-level closure.
decisions_and_assumptions: |
  - Reuse the committed StdioServer process fixture rather than introducing a second JSON-RPC harness. Its test-only ROOT binding is temporarily redirected so python -m practical_agency.mcp_server imports the copied runtime, not the repository package.
  - Reuse the existing _setup, _runtime, _refs, _record, _intent, _read_count, and _schema_errors fixtures to minimize duplication and preserve the already-tested active-mission and dynamic-reader contracts.
  - The observation shim is outside the copied runtime and is added only to the child PYTHONPATH. It changes no practical_agency, hook, skill, contract, checkpoint, or production source byte.
  - One integration test deliberately orders extra-request refusal, valid issue, malformed-evidence refusal, and valid execute against one durable transaction so each negative assertion can compare the exact checkpoint identity surrounding it.
blockers_or_questions: NONE
recommended_next_action: Apply this diff and run python -m unittest tests.test_durable_capability_transaction.DurableCapabilityTransactionRedTests.test_real_stdio_mcp_issue_execute_round_trip_and_nested_fields_fail_closed -v to record the expected valid-issue MCP_PROTOCOL_ERROR RED.
