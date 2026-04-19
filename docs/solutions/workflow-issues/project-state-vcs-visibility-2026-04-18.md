---
title: "Project State Belongs in Version-Controlled Docs, Not RALPH.local.md"
date: 2026-04-18
category: docs/solutions/workflow-issues/
module: ce-workflow
problem_type: workflow_issue
component: development_workflow
severity: medium
root_cause: inadequate_documentation
resolution_type: workflow_improvement
applies_when:
  - Starting a new agent session on the project
  - Working in a fresh environment without RALPH.local.md present
  - Collaborating or handing off the project to another agent or developer
  - Closing a session where state was only written to local scratch files
symptoms:
  - RALPH.local.md absent in new environments — CE step progress and TODOs invisible
  - Agent sessions re-derive state from git log instead of explicit documentation
  - Blocked items and next-steps silently lost between sessions
  - "?? RALPH.md" in git status — the committed state doc was never committed
tags:
  - ralph-loop
  - vcs-visibility
  - project-state
  - workflow
  - agent-context
  - ce-workflow
  - documentation
---

# Project State Belongs in Version-Controlled Docs, Not RALPH.local.md

## Context

During active development of the WDWGN project, running workflow state (CE step completion, implementation summaries, failed attempts, blocked TODOs) accumulated in `RALPH.local.md` — a local scratch file that is not committed to version control. This is by design for ephemeral notes, but in practice it became the sole record of project state.

The mechanical root (session history): `.local.md` files are in `.gitignore`, so committing `RALPH.local.md` required `git add -f` every time — an easily forgotten workaround that also produced intermittent errors. The file occupied an awkward middle ground: gitignored (intentionally local) but force-committed as a workaround.

The gap surfaced concretely: at the start of a new session, `RALPH.local.md` said "ce-work NOT STARTED" when in fact all 14 units were implemented, 147 tests were passing, and ce-review had already run. The agent reconstructed state from git history and the plan doc. That worked, but it is slower and error-prone. Later, a VPS deployment blocker ("no VPS capable of handling a webhook") was written only to `RALPH.local.md` — invisible to any future session.

Meanwhile, `RALPH.md` appeared as `?? RALPH.md` in git status — an untracked file that was meant to be the committed equivalent, never committed.

## Guidance

Any project state that must survive a session restart or be visible to a collaborator must live in a committed file. `RALPH.local.md` and `.claude/ralph-loop.local.md` are ephemeral scratch files — intentionally local. They are not a substitute for committed documentation.

The committed files that carry project state in this project:

**`RALPH.md`** — The CE workflow state document. If it exists as untracked, commit it immediately. It should contain: current CE phase, which steps are complete, any blocked items with the reason, and the next concrete action.

**`docs/plans/[plan].md`** — The implementation plan. As CE steps finish, add completion markers and a deferred/pending section for blocked items. The plan then functions as both a roadmap and a living status document.

**`AGENTS.md`** — Agent-facing context. Add a "Current Status" section that notes the current phase and any blockers relevant to agent-assisted work.

**`README.md`** — A "Current Status" or "Project Status" section makes completion state visible to anyone cloning the repo.

**The rule:** If you would be frustrated to lose the information when `RALPH.local.md` is wiped, it belongs in a committed file. Rough working notes, intermediate failures, and speculative ideas belong in the local file. The question is: does this information affect what a collaborator or future session should do next? If yes, commit it.

## Why This Matters

A repository is a communication medium. When project state lives only in a local scratch file:

- **New sessions start blind.** The agent re-derives state from code and commit history instead of explicit documentation — slower and error-prone.
- **Blocked items become invisible.** "VPS webhook deploy blocked: no VPS provisioned" is critical context for prioritization. If it lives only in a local file, it will be re-discovered the hard way.
- **Institutional memory is fragile.** Scratch files get regenerated, overwritten, or lost. A committed file survives across machines, collaborators, and time.
- **The committed/actual gap grows silently.** By the time it is noticed, significant re-orientation work is needed.

Keeping state in committed files also benefits solo developers: the next working session starts with correct context at no extra cost.

## When to Apply

- A CE step is marked complete → update the plan and `RALPH.md` and commit
- A blocker is identified → record it in `AGENTS.md` and `RALPH.md` with the reason and commit
- A phase transition occurs → update `README.md` current status
- A session is about to end with meaningful state only in the local scratch file → migrate the meaningful parts to committed files before closing
- Verifying handoff quality → ask: do `RALPH.md`, `AGENTS.md`, and the plan together give enough context to orient a reader who has never seen `RALPH.local.md`? If no, commit more.

## Examples

### Before — state lives only in RALPH.local.md (not committed)

`RALPH.local.md` (local, ephemeral, gitignored):
```
Step 7 DONE — handlers wired, routers registered.
Step 8 DONE — Docker + Nginx config finalized.
BLOCKED: VPS deploy — no VPS available. Skipped for now.
Next: write solution docs, then commit RALPH.md.
```

`RALPH.md` — untracked (`?? RALPH.md`), never committed.
`AGENTS.md` — no mention of current phase or blocked items.
Plan doc — no completion markers, no deferred section.

A new session opens the repo. It sees recent commits but cannot tell whether deployment is done, what is blocked, or what to do next.

### After — state distributed across committed files

`RALPH.md` (committed):
```markdown
## CE State — 2026-04-18
All 14 implementation units complete. 147 tests passing.
ce-review: DONE. ce-compound: DONE.

Blocked: VPS webhook deployment — no VPS provisioned. Bot tested in polling mode locally.
Next: provision VPS or mark deployment step as deferred and close.
```

`AGENTS.md` — "Current Status" section added with phase and blocker.

`docs/plans/[plan].md` — steps 1–14 marked complete; deployment step annotated as deferred with reason.

`README.md` — "Current Status" updated to reflect implementation-complete, deployment-pending state.

`RALPH.local.md` — still used for rough notes during the session; nothing critical lives only here.

A new session opens the repo, reads `AGENTS.md` and `RALPH.md`, and immediately knows current state. No reconstruction needed.

## Related

- `RALPH.md` — the committed CE workflow state document for this project; should be committed and kept current
- `docs/plans/2026-04-13-001-feat-social-media-organizer-telegram-bot-plan.md` — implementation plan; natural home for completion markers and a deferred/pending section
- Session history note: the `.local.md` gitignore pattern is correct — these files are intentionally ephemeral. The fix is not to remove them from `.gitignore` but to keep meaningful state in separately committed files
