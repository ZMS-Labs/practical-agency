# Adapter boundary

Practical Agency's deterministic kernel does not perform arbitrary external work.
Adapters implement one narrow protocol, return durable receipts, and never widen
mission authority or manufacture epistemic verdicts.

The initial interfaces are:

- execution dispatch for one authorized action;
- durable checkpoint storage;
- capability descriptor discovery; and
- `watch-commission@1` custody through an upstream verifier and an external
  observer adapter.

No production shell adapter, daemon, scheduler, hosted service, or monitoring
provider is included in v0.1. Fixture adapters prove the contracts only.
