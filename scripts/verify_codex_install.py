#!/usr/bin/env python3
"""Compare source/install runtime bytes and emit a receipt only for a match."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from practical_agency.install_provenance import (  # noqa: E402
    InstallProvenanceError,
    compare_runtime_trees,
)


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--installed", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        comparison = compare_runtime_trees(args.source, args.installed)
    except InstallProvenanceError as error:
        print(str(error), file=sys.stderr)
        return 1
    payload = {"schema": "install-provenance@1", **comparison}
    _atomic_write(args.receipt.resolve(), payload)
    print(
        "install provenance ok: "
        f"files={payload['file_count']} sha256={payload['source_manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
