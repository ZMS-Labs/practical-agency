# Adapters

Production execution, scheduling, and monitoring are **adapters**. The
deterministic kernel in `practical_agency/` never shells out by default and
never duplicates epistemic promotion rules.

## Watch execution adapter

`WatchExecutionAdapter` prepares, proofs, and disables an external observer.
Practical Agency retains receipts and, when available, submits evidence-bound
records to the upstream `watch-commission@1` verifier from epistemic-skills.

If that verifier is unavailable, the custody layer reports
`UNVERIFIED_EXTERNAL_CONTRACT` rather than inventing a second authority.
