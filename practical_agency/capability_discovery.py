"""Dynamic capability discovery without a copied member inventory."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Protocol


class Persistence(str, Enum):
    PROMPT = "prompt"
    SESSION = "session"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    kind: str
    source_ref: str
    source_sha256: str
    description: str
    input_contract: str | None
    output_contract: str | None
    authority_required: tuple[str, ...]
    persistence: Persistence
    independence: str
    availability: str
    degradation_reason: str | None


class CapabilityProvider(Protocol):
    def discover(self) -> list[CapabilityDescriptor]: ...


_FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", re.S)
_SUPPORTED_TOP = {"name", "description", "metadata"}
_SUPPORTED_METADATA = {
    "kind",
    "persistence",
    "independence",
    "authority_required",
    "input_contract",
    "output_contract",
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _list_scalar(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ValueError("UNSUPPORTED_LIST_SYNTAX")
    inner = value[1:-1].strip()
    if not inner:
        return ()
    return tuple(_unquote(part.strip()) for part in inner.split(","))


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse governed fields while treating additive fields as opaque metadata.

    Recognized fields remain strict because they affect authority and dispatch.
    Unknown top-level or metadata keys are deliberately ignored so upstream
    descriptors may add non-authoritative metadata without degrading discovery.
    """

    match = _FRONTMATTER.match(text)
    if not match:
        raise ValueError("MALFORMED_FRONTMATTER")

    result: dict[str, object] = {}
    metadata: dict[str, object] = {}
    in_metadata = False
    skip_nested_after_indent: int | None = None

    for raw in match.group("body").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if raw.startswith("\t"):
            raise ValueError("UNSUPPORTED_FRONTMATTER_INDENTATION")

        if skip_nested_after_indent is not None:
            if indent > skip_nested_after_indent:
                continue
            skip_nested_after_indent = None

        if indent:
            if not in_metadata or indent != 2:
                raise ValueError("UNSUPPORTED_FRONTMATTER_INDENTATION")
            line = raw[2:]
            if ":" not in line:
                raise ValueError("MALFORMED_METADATA")
            key, value = line.split(":", 1)
            key = key.strip()
            scalar = value.strip()
            if key not in _SUPPORTED_METADATA:
                if not scalar or scalar in {"|", ">"}:
                    skip_nested_after_indent = indent
                continue
            if scalar in {"|", ">"}:
                raise ValueError("UNSUPPORTED_MULTILINE_SCALAR")
            metadata[key] = (
                _list_scalar(value)
                if key == "authority_required"
                else _unquote(value)
            )
            continue

        in_metadata = False
        if ":" not in raw:
            raise ValueError("MALFORMED_FRONTMATTER_LINE")
        key, value = raw.split(":", 1)
        key = key.strip()
        scalar = value.strip()
        if key not in _SUPPORTED_TOP:
            if not scalar or scalar in {"|", ">"}:
                skip_nested_after_indent = indent
            continue
        if key == "metadata":
            if scalar:
                raise ValueError("METADATA_MUST_BE_MAPPING")
            in_metadata = True
            result["metadata"] = metadata
        else:
            if scalar in {"|", ">"}:
                raise ValueError("UNSUPPORTED_MULTILINE_SCALAR")
            result[key] = _unquote(value)

    result.setdefault("metadata", metadata)
    return result


def _degraded(path: Path, digest: str, reason: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=path.parent.name,
        kind="skill",
        source_ref=str(path.resolve()),
        source_sha256=digest,
        description="",
        input_contract=None,
        output_contract=None,
        authority_required=(),
        persistence=Persistence.PROMPT,
        independence="either",
        availability="degraded",
        degradation_reason=reason,
    )


class FileSystemSkillProvider:
    def __init__(self, root: Path) -> None:
        self.root = root

    def discover(self) -> list[CapabilityDescriptor]:
        found: list[CapabilityDescriptor] = []
        if not self.root.exists():
            return found
        for child in sorted(path for path in self.root.iterdir() if path.is_dir()):
            path = child / "SKILL.md"
            if not path.is_file():
                continue
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            try:
                parsed = _parse_frontmatter(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as error:
                found.append(_degraded(path, digest, str(error)))
                continue
            metadata = parsed.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            capability_id = str(parsed.get("name") or child.name).strip()
            description = str(parsed.get("description") or "").strip()
            try:
                persistence = Persistence(str(metadata.get("persistence") or "prompt"))
            except ValueError:
                found.append(_degraded(path, digest, "INVALID_PERSISTENCE"))
                continue
            availability = "available"
            degradation: str | None = None
            if not capability_id:
                capability_id = child.name
                availability = "unavailable"
                degradation = "EMPTY_CAPABILITY_ID"
            elif not description:
                availability = "unavailable"
                degradation = "EMPTY_DESCRIPTION"
            authority = metadata.get("authority_required", ())
            if not isinstance(authority, tuple):
                authority = ()
            found.append(
                CapabilityDescriptor(
                    capability_id=capability_id,
                    kind=str(metadata.get("kind") or "skill"),
                    source_ref=str(path.resolve()),
                    source_sha256=digest,
                    description=description,
                    input_contract=(
                        str(metadata["input_contract"])
                        if metadata.get("input_contract")
                        else None
                    ),
                    output_contract=(
                        str(metadata["output_contract"])
                        if metadata.get("output_contract")
                        else None
                    ),
                    authority_required=tuple(str(item) for item in authority),
                    persistence=persistence,
                    independence=str(metadata.get("independence") or "either"),
                    availability=availability,
                    degradation_reason=degradation,
                )
            )
        return found


def discover_capabilities(providers: list[CapabilityProvider]) -> list[CapabilityDescriptor]:
    found = [item for provider in providers for item in provider.discover()]
    counts: dict[str, int] = {}
    for item in found:
        counts[item.capability_id] = counts.get(item.capability_id, 0) + 1
    normalized = [
        replace(
            item,
            availability="unavailable",
            degradation_reason="DUPLICATE_CAPABILITY_ID",
        )
        if counts[item.capability_id] > 1
        else item
        for item in found
    ]
    return sorted(normalized, key=lambda item: (item.capability_id, item.source_ref))
