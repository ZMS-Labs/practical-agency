## DeepReason Docket

- **Mode:** manual-docket
- **Run root / docket path:** `docs/gauntlet-runs/mission-os-v1-design-2026-08-08/deepreason/`
- **Replay status:** not applicable (prose stress-test; no DeepReason MCP)
- **Why used:** operator asked for metacognate + gauntlet + stress-test before treating design as approved; real DeepReason unavailable in this harness.

### Survivor Theories (attack surface)

| Theory | Falsifier | Decision relevance |
| --- | --- | --- |
| T1 Durability theater | Validate manifest with `continuity.deferred_interests` today → must refuse | Blocks “durable defer” claim until schema rule locked |
| T2 Return-point drift under re-plan | Interrupt at index N; rewrite frontier; return original point → must mismatch/rebind | Continuity after capability interrupt |
| T3 Invented ends via absorb/`suggested_next` | Absorb novel aim without amendment → must refuse | Negative power / custody |
| T4 Soft Helix via PA discover→invoke | PA selects named epistemic skill without external routing verdict → fail | Flexibility doctrine |
| T5 Second driver | OS and coordinate_once both mutate frontier in one turn → fail | Single coordination authority |
| T6 Defer parks critical path | Move completion_proof-necessary step to open deferred → fail | Progress honesty |
| T7 High absorb without amendment | open→absorbed high with unchanged amendments → fail | Authority append-only |
| T8 Fixture mistaken for v1 | Cite fixture slice as 1.0 world-power → fail honesty | Claim surface |
| T9 Design self-accept | Author marks design accepted on criteria 2–5 alone → violates iron | Acceptance oracle |

### Refuted Theories

| Theory | Why rejected |
| --- | --- |
| “Second public skill sneaks in via SKILL.md” | Design explicitly forbids; skill inventory remains one — risk is soft product surfaces, not a second SKILL.md (downgraded to P3) |
| “helix it already has special mode” | Live code shows synonym-only normalization; design correctly forbids special behavior |

### Discriminating Tests

| Test | Decides Between | Priority | Status |
| --- | --- | --- | --- |
| Schema validate with deferred_interests | T1 / schema rule | P1 | open until amended design + impl |
| ReturnPoint after frontier rewrite | T2 | P1 | open until amended design + tests |
| Absorb high without amendment | T3/T7 | P1 | open until amended design + tests |
| No PA skill-name map | T4 | P2 | open (design + inventory tests) |
| Sole frontier writer invariant | T5 | P1 | open until amended design |
| Defer vs completion_proof | T6 | P1 | open until amended design |
| Fixture ≠ RELEASE-1.0 claim | T8 | P2 | open (design wording) |

### Docket Limits

This docket expands failure modes for a **design** artifact. It does not prove
implementation correctness, live harness load, or field usefulness.
