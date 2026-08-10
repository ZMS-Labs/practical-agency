schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 57f3d1aa47de94683eaf5d6d983596a9b3d86398
status: PARTIAL
summary: |
  Stage 8 architecture review is complete.

  CURRENT ARCHITECTURE VERDICT: NO-GO.

  The production FileSystemSkillProvider(plugin_root / "skills") plus built-in
  execute_read architecture is not a truthful member-capability boundary. The
  installed Practical Agency package intentionally contains exactly one public
  skill, manifest; the MCP process is rooted in that package; the exposed host
  receipts contain no authoritative external installation/catalog data; and
  capability execution invokes Practical Agency's generic reader rather than a
  method owned by the discovered member. Issuance also lets the MCP caller name
  the capability, blocker, operation, and target instead of deriving a unique
  capability from durable mission state.

  REPLACEMENT ARCHITECTURE VERDICT: GO only behind a host-owned member-capability
  registry and invocation broker. The exact Codex integration exposed by this
  packet provides neither interface, so production implementation against the
  present host substrate remains NO-GO. Practical Agency must fail closed rather
  than simulate discovery by scanning parent directories, accepting caller paths,
  reading an unverified environment inventory, importing member code, spawning a
  command, or falling back to execute_read.

  This was a source and architecture review only. No tests, runtime probes,
  repository mutations, publications, merges, or external messages were performed.
work_product: |
  DECISIVE ARCHITECTURE

  Name: host-attested member-capability transaction.

  Practical Agency remains one public manifest skill and one MCP control plane.
  External/member packages remain independently installed and independently own
  their capability method, trigger contract, output contract, verdict, stopping
  boundary, and coverage limits. Practical Agency owns mission authority,
  selection from the durable blocker, the one-use grant, invocation authorization,
  return-point validation, receipt validation, checkpointing, and refusal behavior.

  1. AUTHORITATIVE MEMBER OBSERVATION

     The host, not the MCP caller and not Practical Agency's package tree, must
     expose a reserved HostCapabilityRegistry interface to the MCP server at
     process startup. Its logical operation is:

       observe_member_capabilities(host_binding)
         -> host-capability-catalog@1

     The transport may be an inherited host RPC channel or equivalent reserved
     substrate, but it must not be represented as an ordinary MCP argument,
     workspace file chosen by the caller, shell command, import path, or mutable
     environment convention.

     Each catalog observation must be immutable and bind at least:

       - host session_id, turn_id, workspace_root, and context-nonce digest;
       - a catalog observation identifier and catalog SHA-256;
       - member package identity and installed-runtime SHA-256;
       - the host-canonical member root;
       - the descriptor path relative to that root;
       - capability_id;
       - descriptor SHA-256;
       - exact input- and output-contract identifiers and SHA-256 values;
       - declared authority requirements and non-mutation posture;
       - exact machine-readable blocker/need kinds owned by the member;
       - an opaque host invocation_ref bound to that package and descriptor; and
       - current availability or a named degradation reason.

     Practical Agency must verify that every descriptor path is a regular,
     non-symlink subject beneath its host-attested root, read the descriptor bytes,
     recompute the descriptor digest, and parse the descriptor through the closed
     descriptor contract. It must not treat the root path or invocation_ref as
     executable instructions.

     This preserves the package invariant enforced by check_package.py: the
     Practical Agency installation still contains only skills/manifest/SKILL.md.
     External roots are host-observed runtime facts, not copied skills, symlinks,
     vendored inventory, or additions to Practical Agency's runtime provenance.

  2. GLOBAL DUPLICATE AND STALENESS CLOSURE

     Discovery must normalize the union of all entries in the authoritative host
     observation, not merely one plugin_root / "skills" directory.

     If more than one current entry has the same capability_id, all such entries
     are unusable, including byte-identical entries. Existing
     DUPLICATE_CAPABILITY_ID degradation semantics should be retained and surfaced
     as CAPABILITY_DESCRIPTOR_UNAVAILABLE. Installation order, path order, caller
     preference, and “first match” must never resolve the ambiguity.

     The durable grant must bind the selected member tuple:

       owner package identity
       owner installed-runtime SHA-256
       descriptor SHA-256
       input-contract SHA-256
       output-contract SHA-256
       opaque invocation_ref
       issue-time catalog observation SHA-256

     Immediately before beginning execution, Practical Agency must obtain a fresh
     host catalog observation and re-read the descriptor. The selected tuple must
     still exist exactly once and retain the same owner, descriptor, contracts,
     non-mutation posture, and invocation_ref. A missing entry or new duplicate
     refuses as CAPABILITY_DESCRIPTOR_UNAVAILABLE; changed bytes or bindings refuse
     as CAPABILITY_DESCRIPTOR_MISMATCH. Refusal occurs before begin, broker
     invocation, member observation, or checkpointed effect.

     A changed unrelated package need not invalidate the grant so long as the
     selected tuple remains identical and globally unique. Both issue-time and
     execute-time catalog digests must nevertheless be retained in the eventual
     invocation receipt for auditability.

  3. BLOCKER-DERIVED SELECTION

     Capability selection is derived from the durable blocker and current
     descriptors. It is not caller-provided.

     The controller must first derive one canonical capability need from the
     latest checkpoint. The minimal durable need record is an internal closed
     capability-need@1 value containing:

       need_id
       blocking_condition copied from current durable mission state
       need_kind
       subject/evidence scope
       required permissions
       expected effects
       estimated costs
       timeout or stop condition
       exact return point

     A free-form frontier sentence without a typed need record is insufficient
     authority and must refuse rather than solicit capability_id, operation, or
     target from the MCP caller.

     Candidate matching uses the need_kind, subject scheme, exact request/result
     contracts, availability, declared authority, and non-mutation posture from
     the freshly observed descriptors:

       zero eligible members -> CAPABILITY_DESCRIPTOR_UNAVAILABLE
       more than one eligible member -> CAPABILITY_SELECTION_AMBIGUOUS
       exactly one eligible member -> eligible for authority evaluation

     No caller-supplied capability ID may break a tie. A caller-provided ID could
     at most be checked as a non-authoritative assertion, but the smallest truthful
     public API removes it.

     Accordingly, manifest_capability_issue should carry no authority-bearing
     capability_id, blocking_condition, admitted_operation, evidence_scope, or
     request supplied by the caller. The controller derives the complete canonical
     request and grant from the checkpointed need and selected descriptor.

  4. MEMBER-OWNED INVOCATION AND VERDICT

     The host must expose a second reserved interface:

       invoke_member_capability(
         host_binding,
         invocation_ref,
         grant_id,
         execution_attempt_id,
         canonical_request_bytes
       ) -> host-capability-invocation-receipt@1

     and, for replacement-process reconciliation:

       lookup_member_invocation(execution_attempt_id)
         -> host-capability-invocation-receipt@1 | NONE

     invocation_ref is an opaque handle to a host-registered member entry. It is
     not a command, Python import, filesystem entry point, generic MCP method name,
     or mutation adapter. The host must reject an invocation_ref that is not bound
     to the cataloged package, descriptor, contracts, and permitted read-only
     invocation class.

     The host invokes the member through its native registered capability
     mechanism. That may internally be a host-managed skill or a sibling typed MCP
     method, but Practical Agency does not execute or reproduce the member's method.

     The member receives the exact canonical capability-request@1 value and returns
     the exact capability-result@1 value governed by its declared output contract.
     The member, not execute_read and not ManifestController, owns:

       - whether its bounded method completed, declined, blocked, or failed;
       - its verdict, including negative or inconclusive verdicts;
       - artifact references;
       - observed effects;
       - coverage limits; and
       - its stopping boundary.

     Practical Agency validates and stores that result verbatim. It must not
     synthesize PASS, reinterpret NO-GO or FAIL, discard coverage limits, manufacture
     observed effects, or fall back to a generic reader when invocation is
     unavailable.

     This Stage 8 member boundary admits only host-registered non-mutating
     invocation classes. Generic shell, dynamic imports, arbitrary subprocesses,
     generic sandbox execution, and mutation handles are not representable.
     Material mutation remains on the separately brokered manifest_dispatch adapter
     path and is outside this member-result boundary.

  5. INVOCATION RECEIPT

     The member result remains unchanged and member-owned. Practical Agency should
     add a separate strict internal host-capability-invocation-receipt@1 wrapper
     rather than adding broker-owned fields to capability-result@1.

     The host-owned receipt must bind:

       schema
       host session_id, turn_id, workspace_root, and context-nonce digest
       issue-time and execute-time catalog observation SHA-256 values
       owner package identity and installed-runtime SHA-256
       capability_id and descriptor SHA-256
       input- and output-contract SHA-256 values
       invocation_ref
       grant_id
       execution_attempt_id
       request_id and canonical request SHA-256
       invocation status
       exact result bytes or result reference
       result SHA-256
       exact returned control point
       external durable receipt reference
       host coverage limits

     The receipt must be written by the host broker, immutable, and retrievable by
     execution_attempt_id. A raw result or receipt object supplied through the
     public MCP call remains forbidden.

  6. DURABLE CONTROL AND DATA FLOW

     a. manifest_engage validates the existing host context and gate receipts and
        loads the highest valid mission checkpoint.

     b. The controller derives one typed capability need from the current durable
        blocker/frontier and exact authority scope.

     c. The controller requests a host catalog observation, verifies all roots and
        descriptor bytes, globally closes duplicate IDs, and derives exactly one
        eligible member. No eligible or unique member leaves the mission visibly
        blocked or degraded.

     d. The controller authorizes the derived permissions, effects, costs,
        protected state, and escalation posture.

     e. The controller creates capability-request@1 and a one-use durable grant.
        The grant binds the need digest, member tuple, request digest, mission
        identity/revision, evidence scope, mutation=false, and exact return point.
        The pending transaction is checkpointed before execution.

     f. manifest_capability_execute accepts grant_id only, in addition to reserved
        host-injected evidence. It reloads the canonical transaction, freshens the
        host catalog, re-observes descriptor and contracts, rechecks authority and
        return point, and refuses any drift before member invocation.

     g. begin_capability_execution consumes the durable grant, records the
        execution_attempt_id and process owner, changes pending to in_progress,
        and is atomically checkpointed before calling the host broker.

     h. The host broker invokes only the catalog-bound member and durably creates
        its invocation receipt.

     i. Practical Agency validates the receipt's host binding, owner tuple,
        invocation_ref, grant ID, attempt ID, request digest, result digest,
        member output contract, request_id, and exact returned control point.

     j. Only the validated member result and host receipt are passed internally to
        record_capability_result. The transaction becomes consumed and is
        checkpointed. The member's exact status, verdict, artifacts, observed
        effects, and coverage limits are preserved.

     k. If the process dies or any post-begin path lacks a valid matching host
        receipt, the existing fail-closed orphan rule remains authoritative:
        execution_state becomes unknown and
        CAPABILITY_EFFECT_UNKNOWN:<grant_id> blocks replay and replacement.
        A replacement process may reconcile only from the host-owned receipt for
        that exact execution_attempt_id; it may not rerun the member.

  7. PUBLIC SURFACE

     The one public skill remains skills/manifest/SKILL.md.

     The MCP tool set may retain the two internal mission operations, but their
     authority-bearing arguments narrow to:

       manifest_capability_issue: no caller selection fields
       manifest_capability_execute: grant_id only

     Reserved host context, gate, registry, and invocation receipt references are
     injected or accessed through the host integration and are never solicited
     from the operator.

     No second public skill, member inventory, generic member-execute tool, caller
     root argument, caller result-submission tool, shell adapter, or mutation
     adapter is introduced.

  8. NAMED FAIL-CLOSED BEHAVIOR

     Preserve existing refusal codes wherever their meaning remains exact:

       HOST_GATE_UNAVAILABLE
       CAPABILITY_DESCRIPTOR_UNAVAILABLE
       DUPLICATE_CAPABILITY_ID
       CAPABILITY_DESCRIPTOR_MISMATCH
       CAPABILITY_CONTRACT_MISMATCH
       CAPABILITY_GRANT_NOT_FOUND
       CAPABILITY_GRANT_NOT_PENDING
       CAPABILITY_EXECUTION_IN_PROGRESS
       CAPABILITY_RESULT_REPLAY
       CAPABILITY_RETURN_POINT_MISMATCH
       CAPABILITY_RESULT_INVALID
       CAPABILITY_EFFECT_UNKNOWN:<grant_id>

     The smallest new host-boundary refusals are:

       HOST_CAPABILITY_REGISTRY_UNAVAILABLE
       HOST_CAPABILITY_REGISTRY_INVALID
       CAPABILITY_SELECTION_AMBIGUOUS
       CAPABILITY_INVOCATION_UNAVAILABLE
       CAPABILITY_INVOCATION_RECEIPT_INVALID
       CAPABILITY_INVOCATION_BINDING_MISMATCH

     Missing host substrate, malformed catalog data, ambiguous selection, stale
     member bindings, invocation transport failure, malformed member output, or an
     unbound receipt must never enter execute_read, dynamically load member code,
     cause a second invocation, or fabricate a capability result.

evidence: |
  INSTALLED PACKAGE AND CHECKS

  - .github/scripts/check_package.py::main enforces that the complete repository
    contains exactly one SKILL.md and that it is skills/manifest/SKILL.md. It also
    requires each package descriptor's skills path to remain ./skills/, validates
    the fixed Codex MCP declaration, copies only the Practical Agency runtime, and
    starts practical_agency.mcp_server from that copied package.
  - .codex-plugin/plugin.json::skills/mcpServers/hooks declares only Practical
    Agency's own ./skills/, ./.mcp.json, and ./hooks/hooks.json. It contains no
    member dependency, external root set, catalog endpoint, or invocation broker.
  - .mcp.json::mcpServers.practical-agency starts python -m
    practical_agency.mcp_server with cwd ".".
  - practical_agency/install_provenance.py::RUNTIME_PATHS includes
    skills/manifest and Practical Agency's own runtime/contracts, but no external
    package roots. build_runtime_manifest and compare_runtime_trees therefore
    prove the installed Practical Agency tree, not an installed member set.
  - pyproject.toml declares no package dependencies and packages only
    practical_agency*.

  CURRENT DISCOVERY

  - practical_agency/capability_discovery.py::FileSystemSkillProvider.discover
    scans one supplied directory's immediate child SKILL.md files and hashes the
    descriptor bytes.
  - practical_agency/capability_discovery.py::discover_capabilities correctly
    degrades every duplicate capability_id to DUPLICATE_CAPABILITY_ID, but only
    over the providers supplied by its caller.
  - practical_agency/controller.py::ManifestController._descriptor supplies only
    FileSystemSkillProvider(self.plugin_root / "skills"). At the packet commit
    that root contains only manifest, whose mission-manifest/checkpoint contracts
    are not the capability-request/capability-result pair.
  - practical_agency/controller.py::ManifestController._observed_descriptor
    rechecks descriptor SHA-256, a control that should be preserved and extended
    across the host-attested global member set.

  MCP AND HOST BINDING

  - practical_agency/mcp_server.py::PLUGIN_ROOT and McpServer.__init__ root the
    controller in the installed Practical Agency package.
  - practical_agency/mcp_server.py::TOOLS exposes caller-provided capability_id,
    blocking_condition, admitted_operation, evidence_scope, operation, and target.
    It contains no catalog receipt or native member invocation handle.
  - practical_agency/host_evidence.py::_CONTEXT_FIELDS,
    practical_agency/host_evidence.py::_GATE_FIELDS, and
    practical_agency/host_evidence.py::validate_host_bindings bind prompt,
    workspace, session, turn, hook definition, tool name, and gate posture. They
    intentionally do not attest installed member roots or an invocation outcome.
  - hooks/manifest_hook.py::handle writes only host context/gate receipts and
    injects _host_context_ref and _host_gate_ref. No available hook field exposes
    the installed member set or a host-native member invocation/result receipt.
  - Therefore the exact packet exposes insufficient host substrate to the MCP
    process. This does not prove that Codex can never implement such a substrate;
    it proves that this installed integration cannot presently consume one.

  CURRENT ISSUE AND EXECUTE PATH

  - practical_agency/controller.py::ManifestController.manifest_capability_issue
    accepts caller-selected capability_id, blocking_condition,
    admitted_operation, evidence_scope, and request. It validates those values but
    does not derive selection from a durable typed blocker.
  - The same method derives the return point from current frontier index zero,
    issues a descriptor-digest-bound one-use grant, records the strict canonical
    request, and checkpoints it. Those durable controls should be retained.
  - practical_agency/controller.py::ManifestController.manifest_capability_execute
    reloads the canonical grant, checks mission revision, operation, target,
    evidence scope, request identity, descriptor digest, contracts, and authority,
    then checkpoints begin_capability_execution.
  - It subsequently calls practical_agency.capability_operations.execute_read and
    constructs capability-result@1 itself. The discovered member's method,
    descriptor body, stopping boundary, and verdict are not invoked.
  - practical_agency/capability_operations.py::execute_read is a Practical
    Agency-owned generic file/resource/web reader. Its base grant result supplies
    PASS, demonstrating that the current verdict is broker-generated rather than
    member-owned.

  DURABLE CONTROLS TO PRESERVE

  - practical_agency/capability_grants.py::issue_grant_from_descriptor binds
    capability identity and descriptor digest without a copied inventory.
  - practical_agency/capability_grants.py::consume_grant enforces mission,
    revision, operation, evidence, return-point, no-mutation, and one-use rules.
  - practical_agency/state_machine.py::record_capability_request stores the
    canonical request/grant and enters pending.
  - practical_agency/state_machine.py::begin_capability_execution consumes the
    durable grant and records execution attempt/owner before observation.
  - practical_agency/state_machine.py::mark_capability_execution_unknown preserves
    the used grant, records unknown, and adds
    CAPABILITY_EFFECT_UNKNOWN:<grant_id> to blockers and unresolved verdicts.
  - practical_agency/state_machine.py::record_capability_result validates strict
    result identity and exact return point before entering consumed.

  COORDINATOR, ADAPTERS, AND CONTRACTS

  - practical_agency/coordinator.py::coordinate_once already expresses a
    REQUEST_CAPABILITY decision and exact return point, but receives
    selected_capability from its caller and protects the decision only in a
    session-local map. It is not production discovery or durable invocation.
  - practical_agency/coordinator.py::apply_capability_result preserves a member
    result's status, verdict, artifacts, effects, coverage, frontier, and negative
    blockers after validating the return point. Those semantics support the
    proposed member-owned result path.
  - practical_agency/coordinator.py::ExecutionAdapter and dispatch_once govern
    material execution adapters. They should not be repurposed as a generic
    member-code executor.
  - adapters/README.md requires bounded typed requests, durable receipts, visible
    failure, no arbitrary shell by default, and no authority inferred from
    adapter capability.
  - contracts/capability-request.schema.json is a closed request envelope binding
    mission identity/revision, capability and descriptor identity, authority
    receipt, expected output contract, stop condition, and exact return point.
  - contracts/capability-result.schema.json is a closed result envelope binding
    request identity, typed status, optional verdict, artifacts, effects,
    coverage, and exact returned control point. It contains no durable host
    invocation or grant receipt, supporting a separate strict wrapper rather than
    broker modification of the member result.

  GOVERNING CONTRACT AND PRESERVED REVIEW

  - skills/manifest/SKILL.md::Iron rules requires “Discover; do not inventory”
    and “Invoke; do not absorb,” explicitly assigning the member its trigger,
    method, output, stopping boundary, and exact verdict.
  - skills/manifest/SKILL.md::Coordination loop requires selection of the
    capability that owns the smallest blocker, an exact return point, preservation
    of negative results, and an explicit blocked state when no execution substrate
    exists.
  - skills/manifest/SKILL.md::Degraded operation forbids reconstructing a missing
    capability from memory.
  - skills/manifest/SKILL.md::Guardrail claim ceiling limits current host evidence
    to host-observed context and covered-tool posture, not a sandbox,
    non-bypassability, or principal identity.
  - AGENTS.md::Invariants requires one public manifest skill, no hard-coded
    capability inventory, no self-certification, external receipts for runtime
    claims, and no arbitrary shell adapter.
  - docs/outsource/durable-capability-transaction/relay/0007-target.md::finding-3
    previously established that production discovers no eligible member, tests
    manufacture descriptors in copied runtimes, and execute_read does not invoke
    the descriptor.
  - The same preserved review's finding-4 established that issuance remains
    caller-selected rather than manifest-selected from the blocker.
requirements: |
  GO/NO-GO — current plugin_root / skills discovery:
    NO-GO. It observes only Practical Agency's own one-skill package and cannot
    truthfully claim production member discovery.

  GO/NO-GO — current built-in execute_read invocation:
    NO-GO. It absorbs the member method, generates the effective verdict inside
    Practical Agency, and supplies no member-owned invocation receipt.

  One public skill:
    PRESERVED. External members remain external installations; no second
    Practical Agency SKILL.md is added.

  No static inventory:
    PRESERVED. The current host catalog is observed at runtime and contains
    package/descriptor bindings, not a repository-maintained capability list or
    stage-to-skill table.

  Authoritative external roots:
    HOST-OWNED. Roots and installed-runtime digests come only from a reserved
    host catalog receipt bound to the current HostBinding. Caller roots, parent
    scans, symlinks, LOCAL.md paths, and unverified environment inventories are
    rejected.

  Duplicate descriptors:
    FAIL CLOSED GLOBALLY. Every duplicate capability_id is unavailable; no
    ordering or caller tie-break is permitted.

  Stale descriptors:
    FAIL CLOSED BEFORE INVOCATION. Re-observe the authoritative catalog,
    descriptor bytes, contract digests, owner runtime, uniqueness, and
    invocation_ref immediately before begin.

  Member method and verdict ownership:
    HOST-NATIVE MEMBER INVOCATION. Practical Agency passes the exact canonical
    request through an opaque registered handle and records the exact typed member
    result without execute_read or verdict synthesis.

  Arbitrary shell and mutation:
    FORBIDDEN. The broker accepts only registered non-mutating member handles and
    has no command, import, subprocess, or generic mutation representation.

  Durable grant and return point:
    PRESERVED AND STRENGTHENED. The grant additionally binds the typed need,
    owner/runtime, contracts, invocation_ref, and canonical request digest.
    Execute accepts grant_id only.

  Invocation and receipt binding:
    REQUIRED. A separate host-owned durable receipt binds host context, both
    catalog observations, descriptor/owner, grant, attempt, request, result, and
    return point. Raw caller result injection remains closed.

  Selection:
    DERIVED FROM DURABLE BLOCKER, NOT CALLER-PROVIDED. Zero or multiple eligible
    descriptors block; the caller does not choose among them.

  Crash/replacement behavior:
    PRESERVE CAPABILITY_EFFECT_UNKNOWN. Only a durable host receipt for the exact
    execution_attempt_id can reconcile a post-begin invocation; otherwise no
    replay or replacement grant is allowed.

  Current Codex substrate:
    INSUFFICIENT AS EXPOSED BY THIS PACKET. The minimum missing integration is a
    host-owned registry plus an opaque invocation/lookup broker available to the
    MCP server outside public tool arguments. Do not simulate it in repository
    code.
decisions_and_assumptions: |
  DECISIONS

  1. Keep check_package.py's exact one-public-skill invariant. Member descriptors
     are not copied into Practical Agency.
  2. Keep PLUGIN_ROOT as Practical Agency's own provenance root; do not redefine
     it as an installation parent or plugin marketplace.
  3. Obtain members only from a host-attested catalog bound to current host
     evidence.
  4. Match one machine-readable durable capability need to one globally unique
     current descriptor.
  5. Remove caller authority over capability ID, blocker, operation, target, and
     scope from issuance; remove operation and target from execution.
  6. Invoke the member through an opaque host-registered handle. Do not import or
     interpret executable metadata.
  7. Preserve the exact member result and place broker bindings in a separate
     strict invocation receipt.
  8. Re-observe descriptor and owner binding before begin, then consume the grant
     durably before host invocation.
  9. Preserve the existing unknown-effect boundary whenever a matching external
     receipt is absent.
  10. Do not use the material ExecutionAdapter protocol as a generic member
      executor.

  TRUST ASSUMPTIONS

  - The host registry is authoritative for the member packages currently
    installed and available to the same host session.
  - Registry and broker channels are reserved host facilities not writable or
    selectable by the MCP caller.
  - The host correctly binds each invocation_ref to the cataloged package,
    descriptor, and native member entry.
  - The host persists invocation receipts before reporting completion and can
    retrieve them by execution_attempt_id after an MCP-process replacement.
  - Descriptor bytes and contract identities supplied by the host can be
    independently re-observed or content-verified by Practical Agency.
  - A member result is a bounded member claim, not whole-mission acceptance or
    proof of distinct principal identity.
  - Existing host receipts continue to prove only host-observed context and
    covered-tool posture. This architecture makes no OS-sandbox,
    non-bypassability, principal-authentication, web, or whole-mission-proof
    claim.
blockers_or_questions: |
  BLOCKER: The exact repository integration has no HostCapabilityRegistry,
  no authoritative installed-member catalog receipt, no opaque sibling/member
  invocation broker, and no durable invocation lookup/receipt contract. The MCP
  server receives only its own plugin_root plus caller JSON and the existing
  context/gate references.

  The minimum host integration contract is therefore:

    observe_member_capabilities(host_binding)
      -> immutable host-capability-catalog@1

    invoke_member_capability(
      host_binding,
      invocation_ref,
      grant_id,
      execution_attempt_id,
      canonical_request_bytes
    ) -> immutable host-capability-invocation-receipt@1

    lookup_member_invocation(execution_attempt_id)
      -> the same immutable receipt or NONE

  Until that contract exists, production member discovery and invocation must
  report HOST_CAPABILITY_REGISTRY_UNAVAILABLE or
  CAPABILITY_INVOCATION_UNAVAILABLE. There is no repository-only substitute that
  satisfies the stated architecture.

  Questions: NONE.
recommended_next_action: |
  Add exactly one RED vertical-slice test named
  test_host_member_is_selected_from_durable_blocker_and_receipt_bound.

  The test should supply a fake implementation of the exact proposed host
  registry/broker contract, not a caller-provided root: the host catalog exposes
  one separately rooted, non-mutating member descriptor that uniquely owns one
  typed durable blocker; manifest_capability_issue is called without capability,
  blocker, operation, target, or scope arguments; manifest_capability_execute is
  called with grant_id only; the fake host invokes the member once; and the member
  returns a valid capability-result@1 with verdict FAIL and explicit coverage
  limits.

  The single test should assert that the external member was invoked exactly
  once, execute_read was never entered, the persisted grant/request/host receipt
  bind the need, owner runtime, descriptor, contracts, invocation_ref, request,
  execution attempt, and exact return point, and the stored result preserves the
  member's FAIL verdict and coverage limits byte-for-byte. It is expected to be
  RED because the current server has no host registry/broker interface, issuance
  still requires caller selection fields, execution still requires
  operation/target, and the controller calls execute_read.
