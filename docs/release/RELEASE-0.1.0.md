# Practical Agency 0.1.0 — release candidate notes

Status: **candidate / unreleased**. Do not tag until independent review and
per-harness loading evidence close.

Tagging `0.1.0` does **not** satisfy
[RELEASE-1.0.0-CRITERIA.md](RELEASE-1.0.0-CRITERIA.md). See
[VERSIONING.md](VERSIONING.md) for the claim-surface ladder.

## PROVEN

- `mission-manifest@1` structural schema + semantic validator
- authority-preserving closed transition table
- atomic checkpoint store with SHA-256 receipts
- dynamic capability discovery without hardcoded skill inventory
- bounded coordinator (one consequential step; no self-accept)
- watch-commission custody that refuses PROVEN without upstream verifier
- in-process end-to-end resumable independently accepted mission fixture

## VERIFIED PER HARNESS

- none yet — Cursor / Claude / generic Agent Skills live loading not recorded

## UNVERIFIED

- production execution adapters
- production watch/monitoring providers
- live package loading and invocation in each harness
- comparative efficacy vs ordinary skilled agents

## NOT CLAIMED

- autonomous background operation
- hosted service / daemon
- universal efficacy
- independent ends for the agent
- automatic `watch` → `manifest` routing without installation and admitted intake
