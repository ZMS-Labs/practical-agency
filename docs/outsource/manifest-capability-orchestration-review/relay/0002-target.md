schema: outsource-relay@1
work_id: manifest-capability-orchestration-review
based_on_commit: 9df8eb6340ca4b12bbb39ba283dd2fb3bc43091e
status: COMPLETE
summary: |
Advisory review complete. The repository preserves exactly one packaged public skill, manifest, and its established filesystem-artifact mission path remains a meaningful, non-ceremonial custody kernel. The capability-orchestration slice at this commit is nevertheless NO-GO for a fresh single-invocation claim.

The production controller does not discover or invoke capabilities from the current harness: it scans only Practical Agency's own skills/ directory, which contains only manifest, while probes manufacture an extra descriptor in a temporary plugin root. A descriptor supplies only an identifier and digest; its authority, input contract, output contract, method, persistence, and independence do not constrain the caller-selected operation.

More critically, capability operations are not authorized by the durable mission record. Mission permissions, protected state, costs, and descriptor authority requirements are not consulted. The controller accepts caller-carried grants and results, performs reads before checking grant consumption, does not compare an executing grant with the stored grant, and records results after checking little more than grant ID, return point, and nonempty evidence references. This permits reachable scope substitution, result injection, and effect-level replay. The emitted request and result objects also contradict the repository's own strict capability-request@1 and capability-result@1 schemas.

File and resource identity checks provide a useful narrow static-filesystem boundary, but reads remain unbounded and occur before grant authorization. The web implementation has concrete redirect SSRF, DNS time-of-check/time-of-use, and unbounded-response defects. The three-capability interruption test proves serialization shape in one process with mocked web retrieval, not durable restart. The process probe is manually orchestrated and carries grants in side files rather than demonstrating autonomous single-invocation coordination.

Steward self-acceptance is correctly rejected at the declared-role layer, and the repository honestly declines to claim authenticated principal separation. However, the public controller cannot persist an independent FAIL or INCONCLUSIVE verdict because it exposes only an acceptance operation while the closed state machine's rejection transition requires an unexposed reason-bearing path.
work_product: |
Advisory source-review analysis only. No repository mutation, publication, commit, pull-request action, message, test execution, or runtime probe was performed.

SINGLE-PUBLIC-SKILL SURFACE: PRESERVED; DYNAMIC ORCHESTRATION: CONTRADICTED.

AGENTS.md, .codex-plugin/plugin.json, and the committed skills/ tree establish one public skill, skills/manifest/SKILL.md. That packaging boundary is sound.

The production discovery path is materially narrower than the operator contract. ManifestController._observed_descriptor and ManifestController.manifest_capability_issue instantiate only FileSystemSkillProvider(self.plugin_root / "skills"). At the packet commit that directory contains only manifest. No controller provider reads other installed plugin roots, host descriptors, PRACTICAL_AGENCY_UPSTREAM_SKILLS_DIR, or a LOCAL.md capability-root binding. manifest_engage neither discovers nor returns capability descriptors.

manifest_capability_issue requires the caller to supply capability_id, admitted_operation, evidence_scope, and an arbitrary request. issue_grant_from_descriptor copies only the descriptor ID and source digest. It ignores authority_required, input_contract, output_contract, kind, persistence, and independence. manifest_capability_execute then calls the generic execute_read; no member skill is invoked and no member method or verdict controls the result.

Therefore the implementation has a reusable filesystem-descriptor parser, but not the claimed path in which one manifest invocation discovers the capability that owns a blocker and invokes that capability according to its own contract. The upstream-root discovery test proves that the provider can scan a supplied directory; it does not connect that directory to the production controller. The controller and process probes create skills/dynamic-reader/SKILL.md inside a temporary copied Practical Agency runtime, so they do not close this production-path gap.

MISSION AUTHORITY DOES NOT GOVERN CAPABILITY READS.

manifest_capability_issue does not compare a descriptor's authority_required with manifest.authority.permissions; it does not inspect protected state, acceptable costs, escalation boundaries, or governed paths. The caller may associate any available descriptor with any operation in {"file.read", "resource.read", "web.search", "web.open"} and any evidence scope.

In the committed package, the available local descriptor is manifest, whose authority_required is empty. An active mission can therefore use that descriptor to mint a grant for a workspace file or network URL without demonstrating that the operator authorized repository reads, network access, that target, or disclosure of its contents. execute_read confines file paths to the workspace but otherwise returns and checkpoints the entire content. Workspace confinement is not equivalent to mission authority.

This directly contradicts the skill's rule that each execution request be authorized against permissions, protected state, costs, and escalation rules.

THE DURABLE GRANT IS NOT THE EXECUTION AUTHORITY.

manifest_capability_execute accepts an entire grant dictionary from the caller. It does not load the stored grant by ID, compare the supplied object with the stored canonical object, re-observe the descriptor digest, or atomically change the durable grant to an in-progress or consumed state before I/O.

execute_read performs the file read or calls _retrieve_web before calling consume_grant. Thus stale, revoked, already-used, malformed, or otherwise inadmissible grants can reach the underlying observation first. For web operations this means an external request can occur before the eventual named refusal.

consume_grant marks only the transient caller dictionary as used. Across MCP calls the dictionary is JSON-decoded anew; the copy retained under manifest.capabilities.invoked[*].grant remains unused. A fresh copy can therefore repeat the operation. record_capability_result will reject the second result as CAPABILITY_RESULT_REPLAY, but only after the second read or network request has already occurred.

A caller can also reuse the ID and return point of a real pending grant while changing the caller-carried admitted operation, scope, descriptor digest, or other fields. execute_read evaluates the forged object. The state machine locates the durable record by the separately supplied grant ID, but validates only that the returned control point equals the stored return point and that evidence_refs is a nonempty list. It does not compare the result to the stored operation, scope, descriptor digest, request, mutation policy, or execution receipt. The forged operation can consequently be recorded against the legitimate grant.

manifest_capability_result is an additional direct injection surface. It accepts an arbitrary mapping and commits it without an execution receipt, provider authentication, schema validation, descriptor re-observation, or binding to the stored request beyond the weak state-machine checks.

manifest_capability_request also accepts a caller-fabricated grant without applying issue_grant. Its revision rule is internally inconsistent with execution: it requires the submitted grant to carry the current manifest revision, then recording the request increments the revision, making that grant stale for the subsequent execute call. The separately implemented manifest_capability_issue avoids this by minting for revision + 1.

THE REQUEST AND RESULT ARE NOT THE COMMITTED TYPED CONTRACTS.

contracts/capability-request.schema.json requires a closed capability-request@1 object containing request ID, mission and revision, capability source digest, bounded action, authority receipt, expected output contract, return point, and timeout or stop condition. Production methods and tests instead accept arbitrary mappings such as {"operation": "file.read"}.

contracts/capability-result.schema.json requires a closed object containing request_id, status, artifact_refs, observed_effects, returned_control_point, and coverage_limits. consume_grant emits grant_id, verdict, and evidence_refs, omits required request_id, status, and artifact_refs, and therefore fails the committed schema's required-fields and additionalProperties: false rules.

state_machine.record_capability_request, state_machine.record_capability_result, and manifest semantic validation do not validate either nested object against those schemas. .github/scripts/check_contracts.py validates that schema documents are syntactically strict and present; it does not validate runtime request/result instances. Green contract checks therefore do not support the typed-result claim.

Capability results are persisted, but they are not VerifierResult proof objects and do not independently satisfy mission completion. tests/test_three_capability_interruption.py adds a separate fixture verifier result before completion. The defensible claim is durable storage of arbitrary capability-result-shaped mappings, not retained typed proof.

FILE AND RESOURCE BOUNDARIES ARE NARROWLY USEFUL BUT INCOMPLETE.

_canonical_relative rejects alternate separators, empty and dot components, path traversal, resolved paths outside the workspace, and detectable symlink/reparse traversal. The focused tests cover alternate file identity and rejection of resource:// identity. Under a static local filesystem, this is a useful bounded-path implementation.

The authorization-order defect remains: content is read before the grant is consumed. Both file and resource reads load and retain the entire UTF-8 file without a size limit. Path validation and read_text are separate operations, leaving a concurrent path-replacement race rather than a descriptor-relative or file-descriptor-relative open. These are concrete residual boundaries, although the repository correctly does not claim an OS sandbox.

resource.read is currently only resource: plus a workspace-relative file path. It does not invoke a resource provider or establish external resource provenance. That is a legitimate narrow scope if described as such, but it is not a distinct external capability substrate.

WEB TARGET VALIDATION IS BYPASSABLE BEFORE REFUSAL.

_retrieve_web validates the initial URL, then uses the default urllib.request.urlopen, which follows redirects. The final URL is checked only after the redirected connection and response have occurred. A public URL redirecting to a loopback, link-local, or private address is therefore contacted before WEB_PRIVATE_TARGET or WEB_REDIRECT_OUT_OF_SCOPE can be raised.

DNS addresses are inspected through a separate socket.getaddrinfo call, while urllib resolves again for the connection. The checked address is not pinned to the connected peer, leaving a DNS-rebinding or resolution-race path.

response.read() is unbounded. The complete response body is decoded, returned, and then retained inside the mission checkpoint, allowing network and durable-state resource exhaustion. The caller-provided evidence_payload is hashed but is not compared with the retrieved response bytes, so it is not proof that the supplied source record is the observed response.

The focused web tests mock _retrieve_web; they establish result-shape behavior after a synthetic response, not redirect, DNS, peer-address, timeout, body-limit, or retention safety.

INTERRUPTION EVIDENCE DOES NOT ESTABLISH THE THREE-CAPABILITY OPERATOR CLAIM.

tests/test_three_capability_interruption.py simulates interruption with MissionManifest.from_dict(manifest.to_dict()) inside one test process. It does not use FileCheckpointStore, mission discovery, a new controller process, a host invocation, or a live web request. Its web operation is mocked, and final completion depends on record_fixture_verifier_result.

scripts/run_capability_controller_probe.py is controller-level fixture code using a manufactured descriptor and explicit caller routing. scripts/run_capability_process_probe.py does start separate Python processes, but a parent script predetermines every issue and execute phase, places each grant in workspace/grant-N.json outside the mission checkpoint contract, and supplies the capability ID, operation, target, and web evidence. Even if executed successfully, it would establish a manually orchestrated process fixture, not one $manifest invocation autonomously discovering and coordinating installed capabilities.

The historical CODEX-MANIFEST-LIVE-ENGAGEMENT-2026-08-09.md is materially stronger documentary evidence for the bounded filesystem-artifact path: it records independent processes, durable discovery, planted drift, brokered repair, steward self-acceptance refusal, and declared-role acceptance. It explicitly does not prove the current three-capability path, OS non-bypassability, authenticated principal separation, or broad production readiness.

ACCEPTANCE HAS AN HONEST CEILING BUT AN INCOMPLETE VERDICT PATH.

The state machine requires the event actor to equal the configured completion acceptor and rejects actors recorded as material workers. externally-proven assurance is deliberately unavailable without principal evidence and an external verifier. Tests cover steward refusal and declared-role acceptance. Those source and test claims are proportionate.

Principal identity remains a caller-provided actor reference, so this is role separation rather than authenticated independence, as the repository correctly states.

The state machine has a reject transition for FAIL or INCONCLUSIVE with a required reason, evidence, and coverage limits. The controller and MCP surface expose only manifest_accept; that method always applies accept or accept_manifest_milestone, supplies no rejection reason, and the acceptance transition requires PASS. Consequently an independent FAIL or INCONCLUSIVE cannot be durably preserved through the public controller path, contradicting skills/manifest/SKILL.md's instruction to preserve those verdicts exactly.

VALUE JUDGMENT AGAINST MANIFEST-TEETH.md.

The established filesystem-artifact vertical path is meaningfully valuable. Removing it would change what can be written, how authority is approved, what survives interruption, how drift is detected, and who may accept completion. That path exhibits negative, continuity, world, and proof power within its declared limits.

The capability-orchestration slice does not yet inherit those teeth. Descriptor records do not constrain the selected operation; mission authority is not checked; the durable grant is not the execution authority; one-use state is transient; results are injectable and schema-incompatible; and interruption tests manually route the work. The slice currently adds durable audit-shaped records around generic reads, but those records do not reliably determine what may occur or what may count as observed proof. A fresh live demonstration would therefore risk validating the happy-path ceremony while leaving the load-bearing authorization and replay falsifiers open.
evidence: |
SOURCE-IMPLEMENTED:

AGENTS.md; .codex-plugin/plugin.json; skills/manifest/SKILL.md; committed skills/ tree: exactly one public skill and explicit single-entry doctrine.

practical_agency/capability_discovery.py::FileSystemSkillProvider and discover_capabilities: dynamic directory scanning, source hashing, degradation, and duplicate-ID detection for explicitly supplied roots.

practical_agency/controller.py::_observed_descriptor, manifest_capability_issue, manifest_capability_request, manifest_capability_execute, and manifest_capability_result: actual production provider choice and request/grant/result path.

practical_agency/capability_grants.py::issue_grant, issue_grant_from_descriptor, and consume_grant: transient one-use flag and actual emitted result shape.

practical_agency/capability_operations.py::_canonical_relative, _safe_web_target, _retrieve_web, and execute_read: file, resource, and web operation order and boundaries.

practical_agency/state_machine.py::record_capability_request, record_capability_result, _require_independent_acceptor, accept, and reject: durable validation and acceptance transitions.

contracts/capability-request.schema.json, contracts/capability-result.schema.json, and .github/scripts/check_contracts.py: strict declared contracts and absence of runtime-instance validation.

practical_agency/mcp_server.py and tests/test_mcp_server.py::TOOL_NAMES: all four capability request/issue/result/execute operations are reachable controller tools during a manifest lock.

hooks/manifest_hook.py::_controller_tool and handle: the host hook allows every Practical Agency manifest_* controller operation while denying other covered tools; it does not distinguish or validate the capability sub-operations.

TEST-COVERED:

Descriptor frontmatter parsing, source-digest changes, duplicate IDs, malformed metadata, and direct scanning of an externally supplied test root.

In-memory grant replay, mission/revision mismatch, mutation refusal, operation mismatch, evidence requirements, and return-point mismatch when the same mutable grant object is reused.

Static file-path identity, local resource: identity, generic read-only operation refusal, and mocked web response recording.

One-process manifest serialization between three generic read cases and declared-role acceptance using a fixture verifier result.

Steward self-acceptance refusal and declared-role acceptance for the filesystem-artifact controller path.

Not covered: canonical stored-grant comparison, MCP/JSON replay before effect, forged same-ID grant substitution, direct result injection, descriptor drift between issue and execute, mission permission/protected-state enforcement, runtime contract validation, negative-verdict controller flow, redirect-before-validation, connected-peer verification, body limits, concurrent file replacement, or autonomous harness-wide selection.

EXTERNALLY REPORTED OR DOCUMENTARY EVIDENCE:

GitHub reports successful deterministic-kernel, Analyze (python), and CodeQL checks for packet commit 9df8eb6340ca4b12bbb39ba283dd2fb3bc43091e. These are repository-hosted check results, not tests independently executed for this review.

The packet commit is one documentation-only commit after baseline 9b83ea9cd4e7144b3eb0304ff48447e41c58e9b2; it adds the handoff and origin relay, so the reviewed implementation is the baseline implementation described by the packet.

docs/release/CODEX-MANIFEST-LIVE-ENGAGEMENT-2026-08-09.md records a prior installed-runtime filesystem-artifact engagement. It is treated as an attributed live-proof report within its explicit claim ceiling, not as independently reproduced evidence.

STILL UNPROVEN:

A fresh installed runtime loading the exact packet-commit implementation rather than a cache copy.

One $manifest invocation discovering real capabilities across installed packages or host descriptors.

Invocation of a member capability according to that member's input, output, authority, method, and stopping contracts.

A durable, authoritative, one-use capability transaction surviving a crash between authorization and effect.

A live three-class interruption run using only mission state and externally durable receipts.

Safe web retrieval across redirects, DNS changes, peer addressing, large responses, and retained-content policy.

Authenticated principal separation, upstream external-provider verification, OS-level non-bypassability, adoption, comparative value, or production readiness.
requirements: |
OUT-001: SATISFIED AS REVIEW; IMPLEMENTATION CONTRADICTED. The single-public-skill package boundary is preserved, but the production controller scans only its own one-skill directory, requires caller selection, ignores member contracts, and never invokes a member capability. Coverage is source-level; no contrary harness runtime evidence exists in the packet.

OUT-002: SATISFIED. Concrete reachable findings cover broker/grant substitution, transient replay, result injection, absent authority enforcement, post-I/O grant checking, file/resource limits, redirect SSRF, DNS rebinding, unbounded web/file retention, interruption evidence limits, and the incomplete negative-acceptance path. Self-acceptance refusal is separately recognized as implemented and test-covered at the declared-role level.

OUT-003: SATISFIED. Source implementation, test coverage, GitHub-reported checks and documentary live proof, and remaining unknowns are separated in the evidence matrix. No probe or test is represented as independently executed.

OUT-004: SATISFIED. The filesystem-artifact custody kernel is judged proportionate and valuable; the capability-orchestration slice is judged insufficiently authoritative to possess the claimed teeth.

OUT-005: SATISFIED. One bounded, ranked capability-transaction hardening patch is specified below with pass/fail evidence and explicit non-goals.

OUT-006: SATISFIED. Review was read-only and advisory. No files, branches, pull requests, issues, messages, runtime state, or repository state were changed.
decisions_and_assumptions: |
DECISION: NO-GO for treating commit 9df8eb6340ca4b12bbb39ba283dd2fb3bc43091e as credible evidence of single-invocation dynamic capability orchestration. This does not invalidate the narrower filesystem-artifact vertical path or the one-public-skill architecture.

DECISION: Do not spend a fresh live mission on the current capability path before the durable grant/result authority defect is closed. A successful happy-path run would not falsify the reachable forged-grant, replay, result-injection, or authority-bypass paths.

DECISION: Preserve the established architecture while repairing it: one public skill, no copied inventory, no generic shell, external observer ownership, closed transitions, append-only authority, and declared-role acceptance ceiling.

ASSUMPTION: Repository source at the immutable packet commit is authoritative for implementation claims. Historical reports and GitHub check conclusions are attributed evidence, not independently reproduced observations.

ASSUMPTION: No undocumented host mechanism co-locates every installed package's skills inside Practical Agency's own plugin root. Even if such a mechanism exists, the controller still lacks member-contract enforcement and invocation, so it would not cure the other findings.
blockers_or_questions: |
BLOCKER — ACTUAL DEFECT: Production discovery is local-only and does not invoke member capabilities.

BLOCKER — ACTUAL DEFECT: Capability operations are not checked against mission permissions, protected state, costs, escalation boundaries, or descriptor authority requirements.

BLOCKER — ACTUAL DEFECT: Caller-carried grants rather than durable stored grants authorize I/O; consumption occurs after I/O; replay and scope substitution can reach effects.

BLOCKER — ACTUAL DEFECT: Arbitrary results can be injected through manifest_capability_result, and runtime request/result objects do not conform to the committed schemas.

BLOCKER — ACTUAL DEFECT: Web redirects are followed before target validation, connection resolution is not bound to the validated address, and response retention is unbounded.

BLOCKER — ACTUAL DEFECT: FAIL and INCONCLUSIVE acceptance verdicts have no reason-bearing controller/MCP transition.

BLOCKER — ASSURANCE GAP: Three-capability process interruption, fresh installed-runtime provenance, authenticated acceptance principals, and OS-level non-bypassability remain unproven.

No operator architecture question is required. The already-approved boundaries determine the safe direction of repair.
recommended_next_action: |
RANK 1 — Implement one bounded “durable capability transaction” hardening patch before attempting another live capability mission.

Required patch boundary:

Make manifest_capability_execute accept a grant_id, not a caller-supplied grant object. Load exactly one canonical pending grant and request from the latest checkpoint.

Before any file access or network operation, re-observe the descriptor digest; verify the stored operation and target; enforce descriptor authority requirements and mission permissions, protected state, costs, and escalation rules; and atomically checkpoint a pending-to-in-progress/consumed transition. A crash after this transition must produce an explicit unknown or blocked result, not automatic replay.

Emit and validate one canonical capability-request@1 and capability-result@1 representation end to end. Either align implementation to the existing strict schemas or intentionally revise the schemas and every producer/consumer together.

Remove manifest_capability_request and manifest_capability_result from the reachable MCP surface until an external provider has a versioned, receipt-bound, authenticated return contract; the internal generic read executor should record its own result.

Fail closed on web.search and web.open in this patch. Do not re-enable them until redirects are disabled or validated before each connection, the connected peer is bound to an allowed resolved address, and response size and retained content are capped.

Add focused controller/MCP adversarial tests proving that a forged same-ID grant, wider scope, stale descriptor, missing mission authority, fresh-copy replay after controller replacement, and direct result injection are all refused before the underlying read/retrieval function is called. Validate generated request and result objects against the committed schemas.

PASS EVIDENCE:

One valid bounded local read executes exactly once across a controller replacement.

The durable checkpoint, not caller JSON, records and controls pending/in-progress/consumed state.

Every negative case asserts zero calls to the file or web executor.

Replaying the original MCP payload cannot perform a second observation.

Runtime request and result instances validate against their strict schemas.

Web operations produce a named pre-network refusal until separately hardened.

FAIL EVIDENCE:

Any invalid or replayed request reaches read_text, urlopen, or an equivalent adapter.

Any caller field can widen the canonical stored operation or scope.

A result can be recorded without the canonical transaction and receipt binding.

A persisted runtime object remains incompatible with its named schema.

NON-GOALS:

Do not add a second public skill, static capability inventory, daemon, scheduler, generic shell adapter, new mutation adapter, principal-authentication claim, or broad orchestration platform.

Do not claim host-wide dynamic discovery or run the fresh three-capability live proof in this patch. Those remain the next bounded integration proof after the transaction itself becomes authoritative.
