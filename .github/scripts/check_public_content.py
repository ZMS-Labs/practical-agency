#!/usr/bin/env python3
"""Reject obvious private topology and credential literals in public content."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yml", ".yaml", ".txt"}
EXCLUDED_NAMES = {"LICENSE"}

HOME_PATH_PATTERN = (
    r"(?:[A-Za-z]:\\Users\\|/" + "home/|/" + "Users/|/" + "mnt/data/)"
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ABSOLUTE_HOME_PATH", re.compile(HOME_PATH_PATTERN, re.I)),
    ("PRIVATE_IPV4", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("LITERAL_CREDENTIAL", re.compile(r"(?i)\b(?:password|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^<${][^'\"\n]{3,}['\"]")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
ALLOWED_EMAILS = {"89846440+sternone@users.noreply.github.com"}


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name in EXCLUDED_NAMES:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"AGENTS.md", ".gitignore"}:
            files.append(path)
    return sorted(files)


def main() -> int:
    errors: list[str] = []
    scanned = 0
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        relative = path.relative_to(ROOT)
        for name, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{name}: {relative}:{line}: {match.group(0)[:80]}")
        for match in EMAIL.finditer(text):
            email = match.group(0).casefold()
            if email not in ALLOWED_EMAILS:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"UNEXPECTED_EMAIL: {relative}:{line}: {match.group(0)}")
    if errors:
        print("public-content check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"public content ok: {scanned} text files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
