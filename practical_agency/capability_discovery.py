"""Dynamic capability discovery from installed skill roots."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Protocol


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


_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _parse_simple_frontmatter(text: str) -> dict[str, str] | None:
    """Parse a deliberately small subset of YAML frontmatter.

    Supports only top-level `key: value` scalars. Nested structures, lists,
    and flow indicators fail closed.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    body = match.group(1)
    result: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-") or ":" not in line:
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or any(ch in key for ch in "[]{}"):
            return None
        if value.startswith(("[", "{")) or value.endswith(("]", "}")):
            return None
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


class FileSystemSkillProvider:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def discover(self) -> list[CapabilityDescriptor]:
        descriptors: list[CapabilityDescriptor] = []
        if not self.root.is_dir():
            return descriptors
        for child in sorted(self.root.iterdir(), key=lambda path: path.name):
            skill = child / "SKILL.md"
            if not child.is_dir() or not skill.is_file():
                continue
            text = skill.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            parsed = _parse_simple_frontmatter(text)
            if parsed is None:
                descriptors.append(
                    CapabilityDescriptor(
                        capability_id=child.name,
                        kind="skill",
                        source_ref=str(skill),
                        source_sha256=digest,
                        description="",
                        input_contract=None,
                        output_contract=None,
                        authority_required=(),
                        persistence=Persistence.PROMPT,
                        independence="member",
                        availability="degraded",
                        degradation_reason="FRONTMATTER_PARSE_FAILED",
                    )
                )
                continue
            name = (parsed.get("name") or child.name).strip()
            description = (parsed.get("description") or "").strip()
            availability = "available"
            reason = None
            if not description:
                availability = "unavailable"
                reason = "EMPTY_DESCRIPTION"
            descriptors.append(
                CapabilityDescriptor(
                    capability_id=name,
                    kind="skill",
                    source_ref=str(skill),
                    source_sha256=digest,
                    description=description,
                    input_contract=None,
                    output_contract=None,
                    authority_required=(),
                    persistence=Persistence.PROMPT,
                    independence="member",
                    availability=availability,
                    degradation_reason=reason,
                )
            )
        return descriptors


def discover_capabilities(roots: Iterable[Path]) -> list[CapabilityDescriptor]:
    found: list[CapabilityDescriptor] = []
    seen: dict[str, CapabilityDescriptor] = {}
    for root in roots:
        for descriptor in FileSystemSkillProvider(Path(root)).discover():
            prior = seen.get(descriptor.capability_id)
            if prior is not None and prior.source_ref != descriptor.source_ref:
                raise ValueError(
                    f"CAPABILITY_ID_CONFLICT: {descriptor.capability_id} found at "
                    f"{prior.source_ref} and {descriptor.source_ref}"
                )
            seen[descriptor.capability_id] = descriptor
            found.append(descriptor)
    return sorted(found, key=lambda item: item.capability_id)
