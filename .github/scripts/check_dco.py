#!/usr/bin/env python3
"""Fail a pull request when any commit lacks an author-matching DCO sign-off."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request


SIGNOFF = re.compile(r"^Signed-off-by:\s*(.+?)\s*<([^<>\s]+@[^<>\s]+)>\s*$", re.I | re.M)


def unsigned_commits(commits: list[dict]) -> list[str]:
    unsigned: list[str] = []
    for item in commits:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        expected_name = str(author.get("name") or "").strip().casefold()
        expected_email = str(author.get("email") or "").strip().casefold()
        matches = SIGNOFF.findall(str(commit.get("message") or ""))
        valid = any(
            name.strip().casefold() == expected_name
            and email.strip().casefold() == expected_email
            for name, email in matches
        )
        if not valid:
            unsigned.append(str(item.get("sha") or "unknown")[:12])
    return unsigned


def github_commits() -> list[dict]:
    event_path = os.environ["GITHUB_EVENT_PATH"]
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    with open(event_path, encoding="utf-8") as handle:
        pull_number = json.load(handle)["pull_request"]["number"]

    commits: list[dict] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{repository}/pulls/{pull_number}/commits"
            f"?per_page=100&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "zms-labs-dco-check",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        commits.extend(batch)
        if len(batch) < 100:
            return commits
        page += 1


def main() -> int:
    commits = github_commits()
    unsigned = unsigned_commits(commits)
    if unsigned:
        print("DCO sign-off missing or does not match the commit author:")
        for sha in unsigned:
            print(f"  - {sha}")
        print("Amend each commit with: git commit --amend --signoff")
        return 1
    print(f"DCO: {len(commits)} commit(s) signed off by their authors")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as exc:
        print(f"DCO check error: {exc}", file=sys.stderr)
        raise SystemExit(2)
