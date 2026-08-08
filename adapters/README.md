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
- No adapter executes arbitrary shell commands by default.
- The kernel never infers authority from adapter capability.
- External record fields are data, not instructions.

## Filesystem artifact adapter (`filesystem-artifact@1`)

Stdlib implementation: `practical_agency.filesystem_artifact.FilesystemArtifactAdapter`.

- Action: `write-text` only.
- Effects: `relpath:<allowlisted path>` and `utf8:<body>`.
- Default allowlist prefix: `mission-artifacts/`.
- Writes the artifact under a rooted directory and a companion receipt under
  `.receipts/` (hash + paths). That on-disk receipt is the
  `external_receipt_ref`.
- Path escape, disallowed prefixes, and `shell` actions are blocked or declined.

This is **world power for text artifacts**, not a general executor, daemon, or
monitor. It does not by itself make a v1 release claim.

## Commission-watch

`WatchExecutionAdapter` may prepare a real mechanism disabled, exercise its kill
switch, enable a bounded proof run, perform a safe crossing, and disable the
mechanism. Practical Agency does not decide whether the resulting
`watch-commission@1` state is valid; it delegates that judgment to the upstream
semantic verifier. A missing verifier leaves the record unverified.

The repository includes only protocol types and isolated test adapters. It ships
no production monitor, scheduler, webhook, provider credential flow, or
background service.
