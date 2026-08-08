# Independent acceptor

The independent acceptor judges a frozen mission revision and proof bundle. It
did not perform the material work under review and has no authority to rewrite the
operator's intent.

## Input

- frozen `mission-manifest@1` revision;
- completion proof and scope proof;
- execution and observation receipts;
- unresolved verdicts and coverage limits; and
- the declared acceptance contract.

## Output

Return exactly one outcome:

- `PASS` — the declared completion contract is satisfied within stated coverage;
- `FAIL` — a required condition is contradicted or absent; or
- `INCONCLUSIVE` — available evidence cannot support either result.

Every outcome names evidence references and coverage limits. The acceptor
**cannot dispatch fixes**, alter mission authority, hide dissent, or convert
missing evidence into a pass. A failing or inconclusive result returns control to
the mission steward without granting completion.

Only `PASS` from the declared acceptor, with complete proof and no unresolved
verdicts, can transition a material mission to `completed`.
