"""Typed, hash-bound verifier results for observed mission artifacts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


class VerifierResultError(ValueError):
    """Named refusal for malformed or unbound verifier evidence."""


_FIELDS = {
    "schema",
    "result_ref",
    "verifier_ref",
    "status",
    "reason_code",
    "proof_ref",
    "subject_ref",
    "mission_id",
    "mission_revision",
    "request_id",
    "adapter_ref",
    "request_sha256",
    "external_receipt_ref",
    "observation",
    "observed_at",
    "coverage_limits",
}
_STATUSES = {"verified", "contradicted", "unverified", "rejected"}


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def canonical_request_sha256(request: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result_ref(payload_without_ref: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload_without_ref),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "verifier-result:sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class VerifierResult:
    result_ref: str
    verifier_ref: str
    status: str
    reason_code: str | None
    proof_ref: str
    subject_ref: str
    mission_id: str
    mission_revision: int
    request_id: str
    adapter_ref: str
    request_sha256: str
    external_receipt_ref: str
    observation: Mapping[str, Any]
    observed_at: str
    coverage_limits: tuple[str, ...]

    @classmethod
    def bind(
        cls,
        *,
        verifier_ref: str,
        status: str,
        proof_ref: str,
        subject_ref: str,
        request: Mapping[str, Any],
        receipt: Mapping[str, Any],
        observation: Mapping[str, Any],
        reason_code: str | None,
        coverage_limits: tuple[str, ...],
        observed_at: str | None = None,
    ) -> "VerifierResult":
        for field, value in (
            ("verifier_ref", verifier_ref),
            ("proof_ref", proof_ref),
            ("subject_ref", subject_ref),
        ):
            if not _nonempty(value):
                raise VerifierResultError(f"VERIFIER_RESULT_{field.upper()}_REQUIRED")
        if status not in _STATUSES:
            raise VerifierResultError("VERIFIER_RESULT_STATUS_INVALID")
        if status == "verified" and reason_code is not None:
            raise VerifierResultError("VERIFIED_RESULT_CANNOT_HAVE_REASON")
        if status != "verified" and not _nonempty(reason_code):
            raise VerifierResultError("NONVERIFIED_RESULT_REASON_REQUIRED")
        if not coverage_limits or any(not _nonempty(item) for item in coverage_limits):
            raise VerifierResultError("VERIFIER_RESULT_COVERAGE_LIMITS_REQUIRED")
        if not isinstance(observation, Mapping):
            raise VerifierResultError("VERIFIER_RESULT_OBSERVATION_REQUIRED")
        if observation.get("artifact_ref") != proof_ref or not _nonempty(
            observation.get("kind")
        ):
            raise VerifierResultError("VERIFIER_RESULT_OBSERVATION_BINDING_MISMATCH")

        mission_id = request.get("mission_id")
        mission_revision = request.get("mission_revision")
        request_id = request.get("request_id")
        adapter_ref = receipt.get("adapter_ref")
        external_receipt_ref = receipt.get("external_receipt_ref")
        if (
            not _nonempty(mission_id)
            or isinstance(mission_revision, bool)
            or not isinstance(mission_revision, int)
            or mission_revision < 1
            or not _nonempty(request_id)
            or receipt.get("mission_id") != mission_id
            or receipt.get("mission_revision") != mission_revision
            or receipt.get("request_id") != request_id
            or not _nonempty(adapter_ref)
            or not _nonempty(external_receipt_ref)
        ):
            raise VerifierResultError("VERIFIER_RESULT_RECEIPT_BINDING_MISMATCH")
        artifact_refs = receipt.get("artifact_refs")
        if not isinstance(artifact_refs, list) or proof_ref not in artifact_refs:
            raise VerifierResultError("VERIFIER_RESULT_ARTIFACT_BINDING_MISMATCH")

        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        core = {
            "schema": "verifier-result@1",
            "verifier_ref": verifier_ref,
            "status": status,
            "reason_code": reason_code,
            "proof_ref": proof_ref,
            "subject_ref": subject_ref,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "request_id": request_id,
            "adapter_ref": adapter_ref,
            "request_sha256": canonical_request_sha256(request),
            "external_receipt_ref": external_receipt_ref,
            "observation": json.loads(json.dumps(dict(observation))),
            "observed_at": timestamp,
            "coverage_limits": list(coverage_limits),
        }
        return cls.from_dict({**core, "result_ref": _result_ref(core)})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerifierResult":
        if not isinstance(payload, Mapping) or set(payload) != _FIELDS:
            raise VerifierResultError("VERIFIER_RESULT_FIELDS_INVALID")
        if payload.get("schema") != "verifier-result@1":
            raise VerifierResultError("VERIFIER_RESULT_SCHEMA_INVALID")
        status = payload.get("status")
        reason_code = payload.get("reason_code")
        if status not in _STATUSES:
            raise VerifierResultError("VERIFIER_RESULT_STATUS_INVALID")
        if status == "verified" and reason_code is not None:
            raise VerifierResultError("VERIFIED_RESULT_CANNOT_HAVE_REASON")
        if status != "verified" and not _nonempty(reason_code):
            raise VerifierResultError("NONVERIFIED_RESULT_REASON_REQUIRED")
        for field in (
            "result_ref",
            "verifier_ref",
            "proof_ref",
            "subject_ref",
            "mission_id",
            "request_id",
            "adapter_ref",
            "request_sha256",
            "external_receipt_ref",
            "observed_at",
        ):
            if not _nonempty(payload.get(field)):
                raise VerifierResultError(f"VERIFIER_RESULT_{field.upper()}_REQUIRED")
        revision = payload.get("mission_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise VerifierResultError("VERIFIER_RESULT_REVISION_INVALID")
        observation = payload.get("observation")
        if (
            not isinstance(observation, Mapping)
            or observation.get("artifact_ref") != payload.get("proof_ref")
            or not _nonempty(observation.get("kind"))
        ):
            raise VerifierResultError("VERIFIER_RESULT_OBSERVATION_BINDING_MISMATCH")
        coverage = payload.get("coverage_limits")
        if (
            not isinstance(coverage, list)
            or not coverage
            or any(not _nonempty(item) for item in coverage)
        ):
            raise VerifierResultError("VERIFIER_RESULT_COVERAGE_LIMITS_REQUIRED")
        core = {key: payload[key] for key in _FIELDS if key != "result_ref"}
        if payload.get("result_ref") != _result_ref(core):
            raise VerifierResultError("VERIFIER_RESULT_HASH_MISMATCH")
        return cls(
            result_ref=str(payload["result_ref"]),
            verifier_ref=str(payload["verifier_ref"]),
            status=str(status),
            reason_code=None if reason_code is None else str(reason_code),
            proof_ref=str(payload["proof_ref"]),
            subject_ref=str(payload["subject_ref"]),
            mission_id=str(payload["mission_id"]),
            mission_revision=int(revision),
            request_id=str(payload["request_id"]),
            adapter_ref=str(payload["adapter_ref"]),
            request_sha256=str(payload["request_sha256"]),
            external_receipt_ref=str(payload["external_receipt_ref"]),
            observation=MappingProxyType(
                json.loads(json.dumps(dict(observation)))
            ),
            observed_at=str(payload["observed_at"]),
            coverage_limits=tuple(str(item) for item in coverage),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "verifier-result@1",
            "result_ref": self.result_ref,
            "verifier_ref": self.verifier_ref,
            "status": self.status,
            "reason_code": self.reason_code,
            "proof_ref": self.proof_ref,
            "subject_ref": self.subject_ref,
            "mission_id": self.mission_id,
            "mission_revision": self.mission_revision,
            "request_id": self.request_id,
            "adapter_ref": self.adapter_ref,
            "request_sha256": self.request_sha256,
            "external_receipt_ref": self.external_receipt_ref,
            "observation": json.loads(json.dumps(dict(self.observation))),
            "observed_at": self.observed_at,
            "coverage_limits": list(self.coverage_limits),
        }
