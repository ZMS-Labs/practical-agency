"""Bounded filesystem artifact adapter with on-disk external receipts.

Stdlib-only. No shell. Writes only under an allowlisted root prefix.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

_ADAPTER_REF = "filesystem-artifact@1"
_RELPATH = re.compile(r"^relpath:(?P<path>.+)$")
_UTF8 = re.compile(r"^utf8:(?P<body>.*)$", re.S)
_SAFE_RELPATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class FilesystemArtifactAdapter:
    """Write text artifacts under a rooted allowlist and emit durable receipts."""

    def __init__(
        self,
        root: Path,
        *,
        allowed_prefixes: tuple[str, ...] = ("mission-artifacts/",),
    ) -> None:
        self.root = Path(root).resolve()
        self.allowed_prefixes = tuple(allowed_prefixes)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".receipts").mkdir(parents=True, exist_ok=True)

    def dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id") or "")
        mission_id = str(request.get("mission_id") or "")
        mission_revision = request.get("mission_revision")
        action = request.get("action")
        effects = request.get("requested_effects")

        base = {
            "schema": "execution-receipt@1",
            "request_id": request_id,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "adapter_ref": _ADAPTER_REF,
            "artifact_refs": [],
            "observed_effects": [],
            "external_receipt_ref": None,
            "coverage_limits": [
                "filesystem-artifact@1 writes text under allowlisted prefixes only",
                "no arbitrary shell",
                "receipt is a local durable file under the adapter root",
            ],
        }

        if action != "write-text":
            return {
                **base,
                "status": "declined",
                "coverage_limits": base["coverage_limits"]
                + [f"unsupported action:{action!r}; no arbitrary shell"],
            }

        if not isinstance(effects, list):
            return {**base, "status": "blocked", "coverage_limits": base["coverage_limits"] + ["effects required"]}

        relpath: str | None = None
        body: str | None = None
        for item in effects:
            if not isinstance(item, str):
                continue
            path_match = _RELPATH.match(item)
            if path_match:
                relpath = path_match.group("path")
                continue
            body_match = _UTF8.match(item)
            if body_match:
                body = body_match.group("body")

        if not relpath or body is None:
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"]
                + ["require relpath: and utf8: effects"],
            }

        if (
            not _SAFE_RELPATH.fullmatch(relpath)
            or ".." in relpath.split("/")
            or relpath.startswith("/")
            or not any(relpath.startswith(prefix) for prefix in self.allowed_prefixes)
        ):
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"]
                + ["relpath outside allowlisted prefixes or unsafe"],
            }

        target = (self.root / relpath).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"] + ["path escape blocked"],
            }

        data = body.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            temp_path.write_bytes(data)
            os.replace(temp_path, target)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

        receipt_path = self.root / ".receipts" / f"{request_id.replace(':', '_')}.json"
        receipt_body = {
            "schema": "filesystem-artifact-receipt@1",
            "adapter_ref": _ADAPTER_REF,
            "request_id": request_id,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "relpath": relpath,
            "artifact_path": str(target),
            "artifact_sha256": digest,
            "bytes": len(data),
        }
        receipt_path.write_text(
            json.dumps(receipt_body, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        return {
            **base,
            "status": "completed",
            "artifact_refs": [f"file:{relpath}"],
            "observed_effects": [
                {
                    "kind": "text-artifact-written",
                    "relpath": relpath,
                    "sha256": digest,
                    "bytes": len(data),
                }
            ],
            "external_receipt_ref": str(receipt_path.resolve()),
        }
