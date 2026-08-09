#!/usr/bin/env python3
"""Codex lifecycle hook for Practical Agency host evidence and tool posture."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from practical_agency.host_evidence import (  # noqa: E402
    HostEvidenceError,
    current_context_ref,
    load_host_context,
    write_host_context,
    write_host_gate,
)
from practical_agency.mission_repository import (  # noqa: E402
    MissionDiscoveryError,
    discover_active_mission,
)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _required(event: Mapping[str, Any], field: str) -> str:
    value = event.get(field)
    if not _nonempty(value):
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    return str(value)


def _explicit_manifest_intent(prompt: str) -> bool:
    normalized = " ".join(prompt.casefold().split())
    return any(
        phrase in normalized
        for phrase in ("$manifest", "manifest this", "helix it", "carry this through")
    )


def _lock_reason(workspace: Path, prompt: str) -> str | None:
    if _explicit_manifest_intent(prompt):
        return "explicit-manifest-intent"
    try:
        discover_active_mission(workspace)
    except MissionDiscoveryError as error:
        if str(error) == "ACTIVE_MISSION_NOT_FOUND":
            return None
        return "unfinished-mission-integrity-error"
    return "unfinished-durable-mission"


def _controller_tool(tool_name: str) -> bool:
    return tool_name.startswith("mcp__practical_agency__manifest_")


def _hook_output(
    event_name: str,
    *,
    decision: str | None = None,
    reason: str | None = None,
    updated_input: Mapping[str, Any] | None = None,
    additional_context: str | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {"hookEventName": event_name}
    if decision is not None:
        output["permissionDecision"] = decision
    if reason is not None:
        output["permissionDecisionReason"] = reason
    if updated_input is not None:
        output["updatedInput"] = dict(updated_input)
    if additional_context is not None:
        output["additionalContext"] = additional_context
    return {"hookSpecificOutput": output}


def handle(event: Mapping[str, Any]) -> dict[str, Any]:
    event_name = _required(event, "hook_event_name")
    workspace = Path(_required(event, "cwd"))
    session_id = _required(event, "session_id")
    turn_id = _required(event, "turn_id")

    if event_name == "UserPromptSubmit":
        prompt = _required(event, "prompt")
        write_host_context(
            workspace_root=workspace,
            prompt=prompt,
            session_id=session_id,
            turn_id=turn_id,
            plugin_root=PLUGIN_ROOT,
        )
        return _hook_output(
            event_name,
            additional_context=(
                "Practical Agency host context is available for this turn. "
                "Reserved receipt references are injected by PreToolUse."
            ),
        )

    if event_name != "PreToolUse":
        raise HostEvidenceError("HOST_CONTEXT_INVALID")

    tool_name = _required(event, "tool_name")
    tool_use_id = _required(event, "tool_use_id")
    raw_input = event.get("tool_input")
    if not isinstance(raw_input, Mapping):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    try:
        context_ref = current_context_ref(
            workspace_root=workspace,
            session_id=session_id,
            turn_id=turn_id,
        )
        context = load_host_context(context_ref, plugin_root=PLUGIN_ROOT)
    except HostEvidenceError:
        if _controller_tool(tool_name):
            return _hook_output(
                event_name,
                decision="deny",
                reason="HOST_GATE_UNAVAILABLE",
            )
        return _hook_output(event_name, decision="allow")

    reason = _lock_reason(Path(context.workspace_root), context.prompt)
    if reason is None:
        if _controller_tool(tool_name):
            return _hook_output(
                event_name,
                decision="deny",
                reason="MANIFEST_ENGAGEMENT_NOT_ACTIVE",
            )
        return _hook_output(event_name, decision="allow")

    if not _controller_tool(tool_name):
        write_host_gate(
            context_ref=context_ref,
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            session_id=session_id,
            turn_id=turn_id,
            workspace_root=workspace,
            lock_reason=reason,
            decision="deny-covered-tool",
            plugin_root=PLUGIN_ROOT,
        )
        return _hook_output(
            event_name,
            decision="deny",
            reason="MANIFEST_ENGAGEMENT_LOCKED",
        )

    gate = write_host_gate(
        context_ref=context_ref,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        session_id=session_id,
        turn_id=turn_id,
        workspace_root=workspace,
        lock_reason=reason,
        decision="allow-controller",
        plugin_root=PLUGIN_ROOT,
    )
    updated = dict(raw_input)
    updated["_host_context_ref"] = context_ref
    updated["_host_gate_ref"] = gate.path
    return _hook_output(
        event_name,
        decision="allow",
        reason="PRACTICAL_AGENCY_CONTROLLER_ALLOWED",
        updated_input=updated,
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw)
        if not isinstance(event, Mapping):
            raise HostEvidenceError("HOST_CONTEXT_INVALID")
        output = handle(event)
    except (HostEvidenceError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
