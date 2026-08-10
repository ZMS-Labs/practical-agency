#!/usr/bin/env python3
"""Enforce the one-skill package surface and resident description budget."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from practical_agency.install_provenance import (  # noqa: E402
    InstallProvenanceError,
    build_runtime_manifest,
)

FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", re.S)
DESCRIPTION_BUDGET_BYTES = 420
CODEX_TOOL_NAMES = [
    "manifest_engage",
    "manifest_capability_issue",
    "manifest_capability_execute",
    "manifest_clarify",
    "manifest_define",
    "manifest_authorize",
    "manifest_dispatch",
    "manifest_verify",
    "manifest_accept",
]


def scalar(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*?)\s*$", frontmatter)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
        value = value[1:-1]
    return value


def _read_json(relative: str, errors: list[str]) -> dict[str, object] | None:
    try:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"PLUGIN_METADATA_INVALID:{relative}:{error}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"PLUGIN_METADATA_INVALID:{relative}:not-object")
        return None
    return payload


def _copy_runtime_plugin(destination: Path) -> None:
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git", "docs", "tests", "missions", "__pycache__", "*.pyc"
        ),
    )


def _mcp_tool_names(installed: Path) -> list[str]:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "check-package", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "-m", "practical_agency.mcp_server"],
        cwd=installed,
        env=environment,
        input="".join(json.dumps(item) + "\n" for item in requests),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"CODEX_MCP_START_FAILED:{completed.stderr.strip()}")
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    if len(responses) != 2:
        raise RuntimeError("CODEX_MCP_PROTOCOL_INVALID")
    if responses[0].get("result", {}).get("serverInfo", {}).get("name") != "practical-agency":
        raise RuntimeError("CODEX_MCP_SERVER_INFO_INVALID")
    return [tool["name"] for tool in responses[1]["result"]["tools"]]


def main() -> int:
    errors: list[str] = []
    try:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(f"PYPROJECT_INVALID:{error}")
    else:
        if project.get("project", {}).get("requires-python") != ">=3.11":
            errors.append("PYTHON_RUNTIME_CONTRACT_INVALID")
    all_skills = sorted(ROOT.rglob("SKILL.md"))
    expected = ROOT / "skills" / "manifest" / "SKILL.md"
    if all_skills != [expected]:
        errors.append(
            "PUBLIC_SKILL_SET_MISMATCH: expected only skills/manifest/SKILL.md; "
            f"found={[str(path.relative_to(ROOT)) for path in all_skills]}"
        )
    if expected.is_file():
        text = expected.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            errors.append("MANIFEST_FRONTMATTER_INVALID")
        else:
            name = scalar(match.group("body"), "name")
            description = scalar(match.group("body"), "description")
            if name != "manifest":
                errors.append(f"MANIFEST_NAME_INVALID:{name!r}")
            if not description:
                errors.append("MANIFEST_DESCRIPTION_MISSING")
            elif len(description.encode("utf-8")) > DESCRIPTION_BUDGET_BYTES:
                errors.append(
                    f"DESCRIPTION_BUDGET_EXCEEDED:{len(description.encode('utf-8'))}>"
                    f"{DESCRIPTION_BUDGET_BYTES}"
                )
            elif "Do NOT use" not in description:
                errors.append("MANIFEST_DECLINE_BOUNDARY_MISSING")

    for relative in (
        "plugin.json",
        ".cursor-plugin/plugin.json",
        ".claude-plugin/plugin.json",
    ):
        path = ROOT / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"PLUGIN_METADATA_INVALID:{relative}:{error}")
            continue
        if payload.get("skills") != "./skills/":
            errors.append(f"PLUGIN_SKILL_ROOT_INVALID:{relative}")

    codex = _read_json(".codex-plugin/plugin.json", errors)
    if codex is not None:
        expected_codex = {
            "skills": "./skills/",
            "mcpServers": "./.mcp.json",
            "hooks": "./hooks/hooks.json",
        }
        for key, expected_value in expected_codex.items():
            if codex.get(key) != expected_value:
                errors.append(f"CODEX_PLUGIN_{key.upper()}_INVALID")
    mcp = _read_json(".mcp.json", errors)
    server = (
        mcp.get("mcpServers", {}).get("practical-agency")
        if isinstance(mcp, dict) and isinstance(mcp.get("mcpServers"), dict)
        else None
    )
    if not isinstance(server, dict) or {
        "cwd": server.get("cwd"),
        "command": server.get("command"),
        "args": server.get("args"),
    } != {
        "cwd": ".",
        "command": "python",
        "args": ["-m", "practical_agency.mcp_server"],
    }:
        errors.append("CODEX_MCP_DECLARATION_INVALID")
    marketplace = _read_json(".agents/plugins/marketplace.json", errors)
    if isinstance(marketplace, dict) and marketplace.get("name") != "practical-agency-dev":
        errors.append("CODEX_MARKETPLACE_NAME_INVALID")
    plugins = marketplace.get("plugins") if isinstance(marketplace, dict) else None
    if not isinstance(plugins, list) or len(plugins) != 1:
        errors.append("CODEX_MARKETPLACE_PLUGIN_SET_INVALID")
    else:
        entry = plugins[0]
        if not isinstance(entry, dict) or entry.get("name") != "practical-agency":
            errors.append("CODEX_MARKETPLACE_PLUGIN_INVALID")
        elif entry.get("source") != {"source": "url", "url": "./"}:
            errors.append("CODEX_MARKETPLACE_SOURCE_INVALID")
        elif entry.get("policy") != {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        }:
            errors.append("CODEX_MARKETPLACE_POLICY_INVALID")

    runtime_file_count = 0
    try:
        runtime_file_count = len(build_runtime_manifest(ROOT)["files"])
    except InstallProvenanceError as error:
        errors.append(str(error))
    mcp_tools: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="pa-package-") as temp:
            installed = Path(temp) / "practical-agency"
            _copy_runtime_plugin(installed)
            mcp_tools = _mcp_tool_names(installed)
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        errors.append(f"CODEX_MCP_EXCHANGE_FAILED:{error}")
    if mcp_tools and mcp_tools != CODEX_TOOL_NAMES:
        errors.append(f"CODEX_MCP_TOOL_SET_INVALID:{mcp_tools!r}")

    if errors:
        print("package check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    description = scalar(
        FRONTMATTER.match(expected.read_text(encoding="utf-8")).group("body"),
        "description",
    )
    print(
        "package ok: one public skill (manifest), "
        f"description_bytes={len((description or '').encode('utf-8'))}/"
        f"{DESCRIPTION_BUDGET_BYTES}, codex_mcp_tools={len(mcp_tools)}, "
        f"runtime_manifest={'verified' if runtime_file_count else 'missing'}, "
        f"runtime_files={runtime_file_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
