# Practical Agency versioning

A release is an immutable support point: one semantic version maps to one Git
commit, one annotated Git tag, one committed release-note file, and one
non-draft GitHub Release when published. `main` is the rolling channel; a
version tag is the reproducible channel.

Version numbers are **claim surfaces**. Bumping a version asserts what the
package may honestly say about operator-authorized mission control. Packaging
vanity is not a reason to tag.

## Semver rules

- **Patch** (`x.y.Z`): compatible correctness, packaging, installation,
  security, or documentation fixes that materially affect users.
- **Minor** (`x.Y.0`): a new internal contract, harness capability, bounded
  adapter, or materially expanded behavior that remains backward compatible
  with the public skill and `mission-manifest@1`.
- **Major** (`X.0.0`): an incompatible change to the public skill trigger or
  output contract, `mission-manifest@N` schema/semantics, installation
  boundary, or package identity — or a new major claim surface (see ladder
  below).

Do not release internal audit prose or relay bookkeeping alone. Release when a
coherent user-visible change has landed and the release gate can bind it to a
verified snapshot.

Gate vocabulary and exception semantics follow the estate pattern used by
epistemic-skills `RELEASING.md`: integrity gates must be met before tag;
harness evidence may degrade to an explicit tier; independent judgment `GO` is
required for a conforming release; owner-authorized publication without `GO` is
an **exception release** recorded as `WAIVED`/`UNMET`, never rewritten as
`PASS`.

## Version ladder

### `0.1.0` — custody kernel support point

First support point for the deterministic mission kernel:

- `mission-manifest@1` structural schema and semantic validator
- authority-preserving closed transitions
- atomic checkpoints with SHA-256 receipts
- dynamic capability discovery without a copied skill inventory
- bounded coordinator (one consequential step; no self-accept)
- watch-commission custody that refuses `PROVEN` without an upstream verifier
- in-process end-to-end resumable, independently accepted mission fixture

`0.1.0` proves **custody and coordination** under fixtures. It does **not** by
itself prove that authorized intent can reach the world through a production
adapter, that every packaged harness loads the skill live, or that missions are
comparatively more effective than ordinary skilled agents.

See [RELEASE-0.1.0.md](RELEASE-0.1.0.md). Tagging `0.1.0` does **not** satisfy
the [1.0.0 criteria](RELEASE-1.0.0-CRITERIA.md).

### `1.0.0` — first operator-useful major

`1.0.0` is reserved for the first version where an operator can honestly use
Practical Agency to **make an authorized intention manifest**:

- installed and callable in every harness declared supported;
- advanced through at least one bounded adapter that emits an **external
  durable receipt** (in-memory fixtures do not qualify);
- resumed after interruption from checkpoints with live-state re-anchoring;
- closed only after an independent acceptor returns `PASS`.

`0.1.0` must be tagged first as an immutable support point, or an explicit
operator exception must record that prerequisite as `WAIVED` (never as `GO`).

Full must-gates, harness rows, adapter and end-to-end proof, watch honesty,
Gauntlet, and anti-claims are in
[RELEASE-1.0.0-CRITERIA.md](RELEASE-1.0.0-CRITERIA.md).

Do **not** rename or retag `0.1.0` as `1.0.0`.

## Public contract freeze at 1.0

While the major line is `1.x`:

- the sole public skill remains `manifest`;
- do not publish separate public skills for resume, checkpoint, reconcile,
  dispatch, commission, or close;
- breaking changes to `mission-manifest@1` require a new major (or a new
  schema epoch with a documented migration);
- production adapters must not run arbitrary shell commands by default;
- the deterministic core remains stdlib-only; adapter dependencies stay
  optional and isolated.

## Anti-claims (any version)

No version may claim, by number alone:

- daemon, hosted service, or autonomous background actor behavior;
- independent ends for the agent;
- universal or comparative efficacy versus ordinary skilled agents;
- automatic `watch` → `manifest` routing without installation and admitted
  intake;
- persistence, scheduling, or observation without an external durable receipt;
- material completion certified by the same actor that performed the work.

Comparative efficacy is a later evidence program. It is not required to define
or tag `1.0.0`, and it must not be implied by the major bump.
