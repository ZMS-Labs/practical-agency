from __future__ import annotations

import copy
import json
from pathlib import Path


def minimal_payload() -> dict[str, object]:
    return json.loads((Path(__file__).parents[1] / "examples" / "minimal-mission.json").read_text(encoding="utf-8"))


def active_payload() -> dict[str, object]:
    payload = copy.deepcopy(minimal_payload())
    payload["revision"] = 2
    payload["state"]["status"] = "active"
    payload["state"]["current_frontier"] = ["create artifact"]
    payload["state"]["next_action"] = "create artifact"
    payload["continuity"]["decisions"] = [
        {"kind": "transition", "from": "draft", "to": "active", "actor_ref": "operator:test", "evidence_ref": "approval:test"}
    ]
    return payload
