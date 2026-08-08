# Attack surface — degraded DeepReason pass

Each mode names its falsifier. Survivors are candidates for findings, not verdicts.

| Mode | Claim under attack | Falsifier |
| --- | --- | --- |
| Authority confusion | Steward can expand beyond operator permissions | `authorize_action` / transition tests reject unprotected expansion |
| Self-certification | Steward can complete a mission | `INDEPENDENT_ACCEPTANCE_REQUIRED` on steward `accept` |
| State corruption | Transitions can assign arbitrary status | closed event table; unknown/illegal events raise |
| Checkpoint forgery | Summary or hash-mismatched file resumes as truth | store rejects hash mismatch; ignores `.tmp` and summaries |
| Immutable revision overwrite | Same revision rewritten with new bytes | `CHECKPOINT_IMMUTABLE` |
| Hardcoded skill inventory | Kernel embeds epistemic skill names | discovery test bans named inventory strings |
| Capability takeover | Member capability keeps control | coordinator return-point request; result must resume |
| Watch promotion smuggling | Adapter success becomes `PROVEN` | `UnverifiedExternalContract` without verifier |
| Description-budget displacement | Skill description exceeds ceiling | 420-byte test |
| Stale resume | Chat summary substitutes for checkpoint | skill + e2e require checkpoint reload |

## Residual risks not closed by unit oracles

| Risk | Why open |
| --- | --- |
| Live harness description drop / misfire | no harness capture on this tip |
| Upstream watch verifier unavailable in field | custody correctly degrades, but operators may over-read `INERT` |
| Fake adapter ≠ production substrate | intentional; production adapters absent |
| One-session gauntlet ≠ independence | orchestration degraded by construction |
