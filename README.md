# Practical Agency

> **Archived on 2026-08-11 and kept as a read-only record. Nothing new is being built here.**
>
> This project was about handing long pieces of work to AI agents, the AI tools that carry out a multi-step task on their own. Its ideas covered recording who authorized the work, where progress was saved and who besides the agent checked the result. Those ideas now live in the [`mission-custody@1` contracts](https://github.com/ZMS-Labs/epistemic-skills/tree/main/plugins/epistemic-skills/contracts/mission-custody) (machine-checkable record formats) in epistemic-skills, added in [PR #114](https://github.com/ZMS-Labs/epistemic-skills/pull/114).
>
> An internal review I ran with AI reviewers on 2026-08-10 came back as a no-go on continuing this repository as it was. The AI judge's summary described the work as "a real, rare, mechanically-demonstrated capability that is currently unwired." None of the reviewers recommended dropping the ideas, and I chose to move them into epistemic-skills. The reasons, the known defects and the conditions for reopening are in the project's decision record, [ADR 0001](docs/adr/0001-park-and-fold-disposition.md).
>
> **Do not install or release from `main`.** The ADR names two defects that block release. First, when a step is refused, the coordinator can re-approve it as a write to a hardcoded example file and send it anyway. The coordinator is the part that picks and sends out the next step. Second, once a reviewer rejects a mission, it can never be accepted. The later branch [`codex/manifest-live-engagement`](https://github.com/ZMS-Labs/practical-agency/tree/codex/manifest-live-engagement) fixed the first defect, and the epistemic-skills version was designed so a failed review can be cleared. All [branches](https://github.com/ZMS-Labs/practical-agency/branches/all) and proof records are preserved.

## Using this today

Use the maintained [`manifest` skill in epistemic-skills](https://github.com/ZMS-Labs/epistemic-skills/tree/main/plugins/epistemic-skills/skills/manifest) instead. A skill is a set of written instructions an AI agent loads for one kind of task. The installation notes below are kept for the record only. Installing this repository's skill next to epistemic-skills would give you two different skills named `manifest`.

## What this was

I wanted AI agents to take the same care every time on work that mattered. The project asked who may act, on what, for how long, when to stop, and what record survives when the chat ends. Each piece of work was a mission, a bounded task with explicit permission, and each mission had a written record called a mission manifest.

AI tools write the code. I decide what each project is for and check what comes back. Here, AI coding agents in three different tools made about 200 commits over four days in August 2026. They started with three competing first versions, and one was kept.

## The mission manifest

A mission manifest is a short file, kept in version control, that answers five questions:

- Intent: what outcome the person wants, in their own words where possible.
- Scope: what is in, what is out, and which environments are touched.
- Authorization: what the agent may do without asking again, and what needs fresh consent.
- Evidence: where proof of progress and completion must be recorded.
- Stop / hold: conditions that pause or end the mission.

The field guide and a template are in [`docs/mission-manifest.md`](docs/mission-manifest.md). The machine-checkable format, `mission-manifest@1`, is defined in [`contracts/mission-manifest.schema.json`](contracts/mission-manifest.schema.json).

The repository's one skill, [`manifest`](skills/manifest/SKILL.md), covers how to open, resume, pause, hand off and close a mission without quietly widening its scope. The code could also keep a record from the epistemic-skills [`watch`](https://github.com/ZMS-Labs/epistemic-skills/tree/main/plugins/epistemic-skills/skills/watch) skill. That skill sets up an outside monitor for something that has to be noticed between sessions. Deciding whether that record was proven stayed with the `watch` skill's own checker.

## Where things stand

Version `0.1.0` was never tagged or released. On 2026-08-08 I [put off tagging it](https://github.com/ZMS-Labs/practical-agency/blob/codex/manifest-live-engagement/docs/release/OPERATOR-WAIVER-DEFER-0.1.0-RELEASE-2026-08-08.md) so the time would go into making it worth using.

`main` holds the first version, merged on 2026-08-07. What was proven, left unverified and not claimed at the time is listed in [RELEASE-0.1.0.md](docs/release/RELEASE-0.1.0.md). Two defects found afterwards are recorded in the ADR.

The later work is on the [unmerged, archived branch `codex/manifest-live-engagement`](https://github.com/ZMS-Labs/practical-agency/tree/codex/manifest-live-engagement). Its own README has no archive notice and still reads as current. The branch includes a script, `scripts/run_controller_process_proof.py`, that runs one mission across three separate processes. It kills each process before starting the next, then checks that the mission picks up where it left off and repairs a changed file. The script lists three limits of its own. Its checks don't wall the agent off at the operating-system level, and it isn't proven that they can't be bypassed. They also don't prove that the worker and the reviewer are different parties. The branch also holds an install check in one tool, recorded on 2026-08-10 (`docs/proofs/2026-08-10-codex-plugin-reinstall-and-catalog.json`).

The review's deciding finding was that the project's own adoption test had never been scheduled. That test asked whether people would use it instead of working around it. Meanwhile the valuable work sat on that one unmerged branch. Whether this approach does better than an ordinary capable AI agent was never measured.

## Installation (kept for the record, not recommended)

These notes describe how the skill was meant to be installed while the project was active. For Cursor, they said to add the repository as a plugin source, or to copy `skills/manifest/` into a project's skills directory and reload the session. For other tools, they gave the generic Agent Skills layout:

```text
your-project/
  .agents/skills/manifest/   # or your tool's skills folder
    SKILL.md
```

The package name in `pyproject.toml` is `zms-practical-agency`, and it was never published to PyPI.

## Tests

This repository is read-only. The tests still run:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q practical_agency tests
```

All 54 tests passed when rerun on 2026-09-23. One end-to-end test, [`tests/test_end_to_end_mission.py`](tests/test_end_to_end_mission.py), runs a mission in a single process. The mission is saved and reloaded, and the worker's own attempt to accept it is refused. A reviewer other than the worker then accepts it. The test does not cover a step that is refused permission, which is where the first defect above sits. No production adapter for external execution is included, and no background service is claimed.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
