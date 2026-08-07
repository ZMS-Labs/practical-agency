# Practical Agency 0.1.0 release boundary

## Included

- one public `manifest` skill;
- deterministic `mission-manifest@1` model and validator;
- authority, lifecycle, capability discovery, bounded coordination, execution
  receipt, checkpoint, and watch-custody modules;
- atomic content-addressed local checkpoints;
- explicit independent acceptance;
- deterministic unit and end-to-end fixtures; and
- fail-closed repository and DCO gates.

## Proven by the deterministic suite

The fixture proves mission intent preservation, dynamic capability discovery,
one-action dispatch, observed artifact hashing, durable checkpoint reload after
all in-memory objects are discarded, contradiction reopening, corrective action,
rejected steward self-acceptance, independent completion, and final checkpoint
recovery.

## Not included or claimed

- no production execution adapter;
- no daemon, scheduler, hosted service, or autonomous background loop;
- no production observer or monitoring provider;
- no authentication of external receipt references by string shape;
- no automatic commission-watch → manifest route without an admitted intake
  contract and supplied upstream verifier;
- no verified loading result for every supported agent harness; and
- no established comparative benefit over an ordinary skilled agent.

## Release gate

Run:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
python .github/scripts/check_repo.py --self-test
python .github/scripts/check_repo.py
python .github/scripts/check_dco.py --self-test
```

A GitHub release or tag additionally requires the exact candidate commit's CI and
DCO checks to conclude successfully and an independent review or an explicitly
recorded degraded-review waiver.
