#!/usr/bin/env python3
"""Require an author-matching Developer Certificate of Origin trailer."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CommitRecord:
    sha: str
    author_name: str
    author_email: str
    message: str


def has_author_signoff(record: CommitRecord) -> bool:
    expected = f"signed-off-by: {record.author_name} <{record.author_email}>".casefold()
    return any(line.strip().casefold() == expected for line in record.message.splitlines())


def _run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def _event_range() -> tuple[str, str] | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pull = payload.get("pull_request")
    if isinstance(pull, dict):
        base = pull.get("base", {}).get("sha")
        head = pull.get("head", {}).get("sha")
        if isinstance(base, str) and isinstance(head, str):
            return base, head
    before, after = payload.get("before"), payload.get("after")
    if isinstance(before, str) and isinstance(after, str) and set(before) != {"0"}:
        return before, after
    return None


def records_for_range(base: str, head: str) -> list[CommitRecord]:
    raw = _run_git(
        "log",
        "--format=%H%x1f%an%x1f%ae%x1f%B%x1e",
        f"{base}..{head}",
    )
    records: list[CommitRecord] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        fields = chunk.split("\x1f", 3)
        if len(fields) != 4:
            raise RuntimeError("unexpected git log record shape")
        records.append(CommitRecord(*fields))
    return records


def self_test() -> list[str]:
    valid = CommitRecord(
        "a" * 40,
        "Example Author",
        "author@example.invalid",
        "change\n\nSigned-off-by: Example Author <author@example.invalid>\n",
    )
    missing = CommitRecord("b" * 40, valid.author_name, valid.author_email, "change\n")
    wrong = CommitRecord(
        "c" * 40,
        valid.author_name,
        valid.author_email,
        "Signed-off-by: Someone Else <else@example.invalid>\n",
    )
    failures: list[str] = []
    if not has_author_signoff(valid):
        failures.append("SELF_TEST_VALID_SIGNOFF_REJECTED")
    if has_author_signoff(missing):
        failures.append("SELF_TEST_MISSING_SIGNOFF_ACCEPTED")
    if has_author_signoff(wrong):
        failures.append("SELF_TEST_WRONG_SIGNOFF_ACCEPTED")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        print("DCO self-test ok")
        return 0

    selected: tuple[str, str] | None = None
    if args.base or args.head:
        if not args.base or not args.head:
            parser.error("--base and --head must be supplied together")
        selected = (args.base, args.head)
    if selected is None:
        selected = _event_range()
    if selected is None:
        head = os.environ.get("GITHUB_SHA") or _run_git("rev-parse", "HEAD").strip()
        base = _run_git("rev-parse", f"{head}^").strip()
        selected = (base, head)

    try:
        records = records_for_range(*selected)
    except RuntimeError as error:
        print(f"DCO_RANGE_ERROR:{error}", file=sys.stderr)
        return 2
    failures = [record for record in records if not has_author_signoff(record)]
    if failures:
        for record in failures:
            print(
                f"DCO_SIGNOFF_MISSING:{record.sha}:{record.author_name} <{record.author_email}>",
                file=sys.stderr,
            )
        return 1
    print(f"DCO ok: {len(records)} commit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
