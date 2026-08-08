# Arbitration — Practical Agency 0.1.0 candidate

**orchestration:** manual-degraded  
**panel:** not isolated (authoring session synthesized attack surface + criticism)

## Findings

### P1

None accepted as open against the frozen tip’s *deterministic* claims.

### P2

1. **P2-HARNESS-LOAD** — Live package loading is unverified for every supported harness.  
   Evidence: freeze premise “Live Cursor/Claude loading…” unestablished.  
   Condition to close: per-harness record with source revision, loaded skill count=1, name=`manifest`, exact description, and accepted `"manifest this"` / `"helix it"` invocation.

2. **P2-INDEPENDENT-ACCEPT** — No independent acceptor has ruled on this candidate.  
   Evidence: this run’s orchestration is `manual-degraded`; metacognate iron forbids self-acceptance.  
   Condition to close: separate human or isolated panel review with explicit PASS/CONDITIONAL/NO-GO on the frozen tip SHA.

3. **P2-PROD-ADAPTER** — No production execution/monitoring adapter is shipped.  
   Evidence: `adapters/README.md` and release notes.  
   Condition to close for *runtime* claims only; not required to tag a deterministic-kernel 0.1.0 if release notes keep UNVERIFIED/NOT CLAIMED boundaries (already present).

### P3 / P4

- P3: repository settings normalization (projects/wiki/squash-only) still operator-admin (API 403 from agent).  
- P4: comparative efficacy unevaluated — correctly unclaimed.

## Computed verdict rule

- Open P1 → NO-GO  
- No open P1, open P2 → **CONDITIONAL**  
- P1+P2 closed → GO  

## Verdict

**CONDITIONAL**

Do **not** tag `v0.1.0` until P2-HARNESS-LOAD and P2-INDEPENDENT-ACCEPT close, or an explicit bounded waiver records which P2 items remain and why tagging proceeds anyway (a waiver is not independence).

## Return point

After P2 closures (or recorded waiver): re-enter release Task 10 Step 6 (tag/PR release) on the same tip or a new tip that re-runs this freeze.
