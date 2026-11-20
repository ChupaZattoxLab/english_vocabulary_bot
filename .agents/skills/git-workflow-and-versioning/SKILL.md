---
name: git-workflow-and-versioning
description: Structures git workflow practices. Use when making any code change. Use when committing, branching, resolving conflicts, splitting uncommitted work in a messy working tree into clean atomic commits, opening or reviewing a pull request (PR), pushing to a remote, or when you need to organize work across multiple parallel streams. Use when cutting a release, choosing a semantic version bump, tagging, or writing a changelog. Name a task branch SCRUM-<number>/<english-slug>, for example SCRUM-32/add-ai-instructions. Several people may share that branch; before editing, update it and main and confirm they do not conflict. Create a commit only after the user has reviewed the diff and asked for that commit.
---

# Git Workflow and Versioning

## Overview

Git is your safety net. Treat commits as save points, branches as sandboxes, and history as documentation. With AI agents generating code at high speed, disciplined version control is the mechanism that keeps changes manageable, reviewable, and reversible.

## When to Use

Always. Every code change flows through git.

## Who Creates the Commit

Prepare the commit. Do not create it.

Show the user the files, the diff, and the message. The user reviews that. Create the commit only after the user asks for that commit. "Commit" in the patterns below means a commit point that is ready for this review.

## One Branch, One Task

One branch holds the complete solution for one task. Name it `SCRUM-<number>/<english-slug>`, for example `SCRUM-32/add-ai-instructions`.

The key matches Jira: uppercase project key, hyphen, number (`SCRUM-32`). The slug is English, lowercase, and hyphen-separated, usually a verb and an object, three to six words. A Russian Jira title is not copied into the name. No type prefix (`feature/`, `fix/`, `refactor/`) and no `task-` prefix: the issue type lives in Jira, and commits on the branch may still mix a behavior change with related refactoring. `main` stays `main`. A hotfix is another Jira task and uses the same pattern.

Every commit for that task stays on that branch. A slice is another commit there, not a new branch and not a second pull request. Merge only when that solution is complete.

Several people can work on that branch at the same time. Before the first edit, fetch and check both tips:

1. The local task branch matches its remote, or fast-forwards to it. Someone else may have pushed since the last session.
2. The fetched `main` is current, and the task branch already contains it or merges with it cleanly.

If either check fails, update before editing. A fast-forward needs a clean working tree. If the update is not a fast-forward, or the merge with `main` conflicts, stop and show the user. Do not start the task on a stale branch or on top of a conflict. Do not rebase or force-push a branch other people are using.

Where the samples below say to merge within a few days, hide unfinished work behind a flag, open a separate pull request, or move part of a task onto another branch, keep the work on this branch instead. Smaller commits on this branch are still right. A second branch for part of the same task is not.

## Core Principles

### Trunk-Based Development (Recommended)

For this repository, `One Branch, One Task` replaces the 1–3 day branch below. `main` stays deployable because the branch merges only when the task solution is complete.

Keep `main` always deployable. Work in short-lived feature branches that merge back within 1-3 days. Long-lived development branches are hidden costs — they diverge, create merge conflicts, and delay integration. DORA research consistently shows trunk-based development correlates with high-performing engineering teams.

```
main ──●──●──●──●──●──●──●──●──●──  (always deployable)
        ╲      ╱  ╲    ╱
         ●──●─╱    ●──╱    ← short-lived feature branches (1-3 days)
```

This is the recommended default. Teams using gitflow or long-lived branches can adapt the principles (atomic commits, small changes, descriptive messages) to their branching model — the commit discipline matters more than the specific branching strategy.

- **Dev branches are costs.** Every day a branch lives, it accumulates merge risk.
- **Release branches are acceptable.** When you need to stabilize a release while main moves forward.
- **Feature flags > long branches.** Prefer deploying incomplete work behind flags rather than keeping it on a branch for weeks.

### 1. Commit Early, Commit Often

Each successful increment gets its own commit. Don't accumulate large uncommitted changes.

```
Work pattern:
  Implement slice → Test → Verify → Show the diff → User asks → Commit → Next slice

Not this:
  Implement everything → Hope it works → Giant commit
```

Commits are save points. If the next change breaks something, you can revert to the last known-good state instantly.

### 2. Atomic Commits

Each commit does one logical thing:

```
# Good: Each commit is self-contained
git log --oneline
a1b2c3d Add task creation endpoint with validation
d4e5f6g Add task creation form component
h7i8j9k Connect form to API and add loading state
m1n2o3p Add task creation tests (unit + integration)

# Bad: Everything mixed together
git log --oneline
x1y2z3a Add task feature, fix sidebar, update deps, refactor utils
```

### 3. Descriptive Messages

Commit messages explain the *why*, not just the *what*:

```
# Good: Explains intent
feat: add email validation to registration endpoint

Prevents invalid email formats from reaching the database.
Uses Zod schema validation at the route handler level,
consistent with existing validation patterns in auth.ts.

# Bad: Describes what's obvious from the diff
update auth.ts
```

**Format:**
```
<type>: <short description>

<optional body explaining why, not what>
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `refactor` — Code change that neither fixes a bug nor adds a feature
- `test` — Adding or updating tests
- `docs` — Documentation only
- `chore` — Tooling, dependencies, config

### 4. Keep Concerns Separate

A task often turns up related code that needs refactoring. That refactor belongs to the task: same branch, its own commit (`One Branch, One Task`). Do not mix it into the commit that changes behavior, and do not open another branch for it. Formatting stays in its own commit too. Unrelated cleanup stays out of the task.

```
# Good: Separate concerns
git commit -m "refactor: extract validation logic to shared utility"
git commit -m "feat: add phone number validation to registration"

# Bad: Mixed concerns
git commit -m "refactor validation and add phone number field"
```

The separate commits are easier to review, revert, and understand in history. A small cleanup, such as renaming a variable, can stay inside the behavior commit.

### 5. Size Your Changes

Target ~100 lines per commit. The task branch may be larger, because it holds the whole task (`One Branch, One Task`). Split a large diff into more commits on that branch, not into another branch. See the splitting strategies in `code-review-and-quality` for how to break a commit down.

```
~100 lines  → Easy to review, easy to revert
~300 lines  → Acceptable for a single logical change
~1000 lines → Split into smaller changes
```

## Branching Strategy

For this repository, follow `One Branch, One Task`, including the branch name. The 1–3 day limit below is a sample from the general text.

### Feature Branches

```
main (always deployable)
  │
  ├── SCRUM-32/add-ai-instructions   ← one task, the complete solution
  └── SCRUM-33/send-paired-audio     ← a different task, in parallel
```

- Branch from `main` (or the team's default branch)
- Name the branch `SCRUM-<number>/<english-slug>`
- Keep branches short-lived (merge within 1-3 days) — long-lived branches are hidden costs
- Delete branches after merge
- Prefer feature flags over long-lived branches for incomplete features

### Branch Naming

```
SCRUM-<number>/<english-slug>  → SCRUM-32/add-ai-instructions
```

## Working with Worktrees

A worktree is for a different task. People working on the same task share that task branch and update it first, as in `One Branch, One Task`. For parallel work on different tasks, use git worktrees:

```bash
# Create a worktree for a task branch
git worktree add ../scrum-32 SCRUM-32/add-ai-instructions
git worktree add ../scrum-33 SCRUM-33/send-paired-audio

# Each worktree is a separate directory with its own branch
# Agents can work in parallel without interfering
ls ../
  project/      ← main branch
  scrum-32/     ← SCRUM-32/add-ai-instructions
  scrum-33/     ← SCRUM-33/send-paired-audio

# When done, merge and clean up
git worktree remove ../scrum-32
```

Benefits:
- Multiple agents can work on different features simultaneously
- No branch switching needed (each directory has its own branch)
- If one experiment fails, delete the worktree — nothing is lost
- Changes are isolated until explicitly merged

## The Save Point Pattern

```
Fetch. Task branch and main are current, and the branch merges with main cleanly
    │
    ├── Makes a change
    │   ├── Test passes? → Show the diff → User asks → Commit → Continue
    │   └── Test fails? → Revert to last commit → Investigate
    │
    ├── Makes another change
    │   ├── Test passes? → Show the diff → User asks → Commit → Continue
    │   └── Test fails? → Revert to last commit → Investigate
    │
    └── Feature complete → All commits form a clean history
```

This pattern means you never lose more than one increment of work. If an agent goes off the rails, `git reset --hard HEAD` takes you back to the last successful state.

## Change Summaries

After any modification, provide a structured summary. This makes review easier, documents scope discipline, and surfaces unintended changes:

```
CHANGES MADE:
- src/routes/tasks.ts: Added validation middleware to POST endpoint
- src/lib/validation.ts: Added TaskCreateSchema using Zod

THINGS I DIDN'T TOUCH (intentionally):
- src/routes/auth.ts: Has similar validation gap but out of scope
- src/middleware/error.ts: Error format could be improved (separate task)

POTENTIAL CONCERNS:
- The Zod schema is strict — rejects extra fields. Confirm this is desired.
- Added zod as a dependency (72KB gzipped) — already in package.json
```

This pattern catches wrong assumptions early and gives reviewers a clear map of the change. The "DIDN'T TOUCH" section is especially important — it shows you exercised scope discipline and didn't go on an unsolicited renovation.

## Pre-Commit Hygiene

Before every commit:

```bash
# 1. Check what you're about to commit
git diff --staged

# 2. Ensure no secrets
git diff --staged | grep -i "password\|secret\|api_key\|token"

# 3. Run tests
npm test

# 4. Run linting
npm run lint

# 5. Run type checking
npx tsc --noEmit
```

Automate this with git hooks:

```json
// package.json (using lint-staged + husky)
{
  "lint-staged": {
    "*.{ts,tsx}": ["eslint --fix", "prettier --write"],
    "*.{json,md}": ["prettier --write"]
  }
}
```

## Handling Generated Files

- **Commit generated files** only if the project expects them (e.g., `package-lock.json`, Prisma migrations)
- **Don't commit** build output (`dist/`, `.next/`), environment files (`.env`), or IDE config (`.vscode/settings.json` unless shared)
- **Have a `.gitignore`** that covers: `node_modules/`, `dist/`, `.env`, `.env.local`, `*.pem`

## Using Git for Debugging

```bash
# Find which commit introduced a bug
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>
# Git checkouts midpoints; run your test at each to narrow down

# View what changed recently
git log --oneline -20
git diff HEAD~5..HEAD -- src/

# Find who last changed a specific line
git blame src/services/task.ts

# Search commit messages for a keyword
git log --grep="validation" --oneline
```

## Release & Versioning

Commits are how *you* track change; a **version** is how your *consumers* track it. The moment anything else depends on your code — another team, a published package, a deployed client — "latest on main" stops being a sufficient answer to "what am I running, and is it safe to upgrade?" A version number and a changelog are the contract that answers it.

### Semantic Versioning

For anything with consumers, version `MAJOR.MINOR.PATCH` and let the number carry meaning:

```
  MAJOR  breaking change — consumers must change their code to upgrade
  MINOR  new functionality, backward-compatible — safe to upgrade
  PATCH  bug fix, backward-compatible — safe to upgrade
```

The number is a promise, so make the code match it. A "patch" that changes behavior consumers relied on is a major change wearing a disguise (Hyrum's Law — see the `api-and-interface-design` skill). When unsure whether a change is breaking, assume it is; a surprise major is far cheaper than a broken consumer.

### Tag the release, and let the tag be the source of truth

A release is an immutable point in history, not a moving branch. Tag it so it can always be reproduced:

```bash
git tag -a v1.4.0 -m "Release 1.4.0"
git push origin v1.4.0
```

Derive the version from the tag rather than hand-editing it in scattered files, so the artifact, the tag, and the changelog can never disagree.

### Keep a changelog written for humans

A changelog is not `git log`. It's the curated, consumer-facing answer to "what changed and do I care?" — grouped by `Added / Changed / Fixed / Deprecated / Removed / Security`, newest on top, every entry phrased around user impact, not internal mechanics.

```markdown
## [1.4.0] - 2025-06-12
### Added
- Bulk task import via CSV
### Fixed
- Timezone drift in recurring task due dates
### Deprecated
- `GET /v1/tasks/all` — use the paginated `GET /v1/tasks` (removal in 2.0)
```

Write the entry in the same change that makes the change, while the impact is fresh — not reconstructed from commit archaeology at release time. Breaking changes get a migration note and a deprecation window (follow the `deprecation-and-migration` skill); shipping the actual release is the `shipping-and-launch` skill's job — this section is the versioning contract that feeds it.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'll commit when the feature is done" | One giant commit is impossible to review, debug, or revert. Commit each slice. |
| "The message doesn't matter" | Messages are documentation. Future you (and future agents) will need to understand what changed and why. |
| "I'll squash it all later" | Squashing destroys the development narrative. Prefer clean incremental commits from the start. |
| "Branches add overhead" | One branch per task keeps that task's commits together. Do not split one task across branches to make each branch short. |
| "I'll split this change later" | Split a large diff into commits on the task branch before review. Do not open another branch for part of the same task. |
| "My local branch is recent enough" | Several people can push to the same task branch, and `main` moves too. Fetch both and confirm there is no conflict before editing. |
| "I don't need a .gitignore" | Until `.env` with production secrets gets committed. Set it up immediately. |
| "It's just a small fix, bump the patch" | Check what consumers can observe. A behavior change they relied on is a major, whatever the diff size. |
| "The changelog is just the commit log" | Commits are for you; the changelog is for consumers, curated by impact. Generating one from raw commits buries what matters. |
| "We'll write the changelog at release time" | By then the impact is reconstructed from memory and half of it is missing. Write the entry with the change. |

## Red Flags

- Large uncommitted changes accumulating
- Commit messages like "fix", "update", "misc"
- Formatting changes mixed with behavior changes
- No `.gitignore` in the project
- Committing `node_modules/`, `.env`, or build artifacts
- A branch that mixes several tasks, or a second branch that holds only part of one task
- Starting work while the task branch is behind its remote, behind `main`, or conflicting with `main`
- Force-pushing to shared branches
- A breaking change shipped under a minor or patch version bump
- A release with no tag, or a version number hand-edited out of sync with the tag
- A user-facing release with no changelog entry, or a changelog that's just dumped commit messages

## Verification

Before the first edit:

- [ ] The task branch is up to date with its remote
- [ ] `main` is up to date, and the task branch merges with it without conflicts

For every commit:

- [ ] The user has reviewed the diff and asked for this commit
- [ ] Commit does one logical thing
- [ ] Message explains the why, follows type conventions
- [ ] Tests pass before committing
- [ ] No secrets in the diff
- [ ] No formatting-only changes mixed with behavior changes
- [ ] `.gitignore` covers standard exclusions

For every release (anything with consumers):

- [ ] The version bump matches the change: breaking → major, additive → minor, fix → patch
- [ ] The release is tagged, and the version is derived from the tag, not hand-edited out of sync
- [ ] The changelog has a curated, human-readable entry grouped by impact for this version
