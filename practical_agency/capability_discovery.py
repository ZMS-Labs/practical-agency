"""Dynamic capability discovery without a copied member inventory."""
from __future__ import annotations

import ast
import hashlib
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


class FrontmatterError(ValueError):
    pass


def _scalar(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[0] in "[{":
        raise FrontmatterError("unsupported structured scalar")
    if value.startswith(("'", '"')):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise FrontmatterError(f"invalid quoted scalar: {error}") from error
        if not isinstance(parsed, str):
            raise FrontmatterError("quoted scalar must be string")
        return parsed
    return value


def _string_list(raw: str) -> tuple[str, ...]:
    value = raw.strip()
    if not value:
        return ()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return ()
        return tuple(_scalar(item) for item in inner.split(","))
    return tuple(item.strip() for item in value.split(",") if item.strip())


def parse_frontmatter(text: str) -> tuple[dict[str, str], dict[str, str]]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise FrontmatterError("missing opening delimiter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise FrontmatterError("missing closing delimiter")
    lines = normalized[4:end].splitlines()
    top: dict[str, str] = {}
    metadata: dict[str, str] = {}
    in_metadata = False
    for line_no, line in enumerate(lines, start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  "):
            if not in_metadata or line.startswith("    ") or ":" not in line:
                raise FrontmatterError(f"unsupported indentation at line {line_no}")
            key, raw = line.strip().split(":", 1)
            if key in metadata:
                raise FrontmatterError(f"duplicate metadata key {key}")
            metadata[key] = raw.strip()
            continue
        in_metadata = False
        if ":" not in line:
            raise FrontmatterError(f"missing colon at line {line_no}")
        key, raw = line.split(":", 1)
        if key not in {"name", "description", "metadata"}:
            raise FrontmatterError(f"unsupported top-level key {key}")
        if key == "metadata":
            if raw.strip():
                raise FrontmatterError("metadata must be a mapping")
            in_metadata = True
            continue
        if key in top:
            raise FrontmatterError(f"duplicate top-level key {key}")
        top[key] = _scalar(raw)
    return top, metadata


class FileSystemSkillProvider:
    def __init__(
        self, root: Path, *, source_root_ref: str = "skills://filesystem"
    ) -> None:
        self.root = Path(root)
        normalized = source_root_ref.strip().rstrip("/")
        if not normalized:
            raise ValueError("SOURCE_ROOT_REF_REQUIRED: source_root_ref must be non-empty")
        self.source_root_ref = normalized

    def discover(self) -> list[CapabilityDescriptor]:
        if not self.root.exists():
            return []
        descriptors: list[CapabilityDescriptor] = []
        for child in sorted(path for path in self.root.iterdir() if path.is_dir()):
            skill = child / "SKILL.md"
            if not skill.is_file():
                continue
            data = skill.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            try:
                text = data.decode("utf-8")
                top, metadata = parse_frontmatter(text)
                capability_id = top.get("name", "").strip()
                if not capability_id:
                    raise FrontmatterError("NAME_REQUIRED: frontmatter.name must be non-empty")
                description = top.get("description", "")
                persistence_raw = metadata.get("persistence", "prompt")
                try:
                    persistence = Persistence(persistence_raw)
                except ValueError as error:
                    raise FrontmatterError(f"invalid persistence {persistence_raw}") from error
                independence = metadata.get("independence", "either")
                if independence not in {"actor", "reviewer", "either"}:
                    raise FrontmatterError(f"invalid independence {independence}")
                availability = "available" if description.strip() else "unavailable"
                degradation = None if availability == "available" else "EMPTY_DESCRIPTION"
                descriptor = CapabilityDescriptor(
                    capability_id=capability_id,
                    kind=metadata.get("kind", "skill"),
                    source_ref=f"{self.source_root_ref}/{child.name}/SKILL.md",
                    source_sha256=digest,
                    description=description,
                    input_contract=metadata.get("input_contract") or None,
                    output_contract=metadata.get("output_contract") or None,
                    authority_required=_string_list(metadata.get("authority_required", "")),
                    persistence=persistence,
                    independence=independence,
                    availability=availability,
                    degradation_reason=degradation,
                )
            except (UnicodeDecodeError, FrontmatterError) as error:
                descriptor = CapabilityDescriptor(
                    capability_id=child.name,
                    kind="skill",
                    source_ref=f"{self.source_root_ref}/{child.name}/SKILL.md",
                    source_sha256=digest,
                    description="",
                    input_contract=None,
                    output_contract=None,
                    authority_required=(),
                    persistence=Persistence.PROMPT,
                    independence="either",
                    availability="degraded",
                    degradation_reason=f"MALFORMED_FRONTMATTER:{error}",
                )
            descriptors.append(descriptor)
        return descriptors


def discover_capabilities(providers: list[CapabilityProvider]) -> list[CapabilityDescriptor]:
    descriptors = [descriptor for provider in providers for descriptor in provider.discover()]
    counts: dict[str, int] = {}
    for descriptor in descriptors:
        counts[descriptor.capability_id] = counts.get(descriptor.capability_id, 0) + 1
    normalized: list[CapabilityDescriptor] = []
    for descriptor in descriptors:
        if counts[descriptor.capability_id] > 1:
            descriptor = replace(
                descriptor,
                availability="unavailable",
                degradation_reason=f"DUPLICATE_CAPABILITY_ID:{descriptor.capability_id}",
            )
        normalized.append(descriptor)
    return sorted(normalized, key=lambda item: (item.capability_id, item.source_ref))
