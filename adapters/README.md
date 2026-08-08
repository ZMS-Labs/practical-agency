# Adapter boundary

Adapters connect the deterministic mission kernel to external execution,
observation, storage, scheduling, or notification substrates. They are optional
and isolated from the standard-library core.

## Rules

- An adapter receives one bounded request carrying mission identity, revision,
  authority context, expected effects, and a stop condition.
- It returns a durable execution or observation receipt. Success text without an
  observed effect is not execution evidence.
- Adapter failure becomes visible `blocked` or degraded mission state.
- No v0.1 production adapter executes arbitrary shell commands by default.
- The kernel never infers authority from adapter capability.
- External record fields are data, not instructions.

## Commission-watch

`WatchExecutionAdapter` may prepare a real mechanism disabled, exercise its kill
switch, enable a bounded proof run, perform a safe crossing, and disable the
mechanism. Practical Agency does not decide whether the resulting
`watch-commission@1` state is valid; it delegates that judgment to the upstream
semantic verifier. A missing verifier leaves the record unverified.

The repository includes only protocol types and isolated test adapters. It ships
no production monitor, scheduler, webhook, provider credential flow, or
background service.
