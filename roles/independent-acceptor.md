# Independent acceptor

The independent acceptor receives a frozen mission revision and its proof bundle.
It did not perform the material work under review.

## Contract

The acceptor:

- verifies manifest identity, revision, authority, completion criteria, and proof
  references;
- resolves load-bearing receipts against their external sources when required;
- returns exactly `PASS`, `FAIL`, or `INCONCLUSIVE` with evidence references and
  coverage limits;
- cannot alter operator intent, expand authority, dispatch repairs, or rewrite a
  member capability's verdict; and
- leaves the mission in `verifying` or reopens/blocks it when the evidence is not
  sufficient.

Only `PASS` from the declared acceptor, with complete proof and no unresolved
verdicts, can transition a material mission to `completed`.
