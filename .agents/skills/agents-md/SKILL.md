---
name: agents-md
description: Assembles or refreshes the root AGENTS.md from the repository and a short future-orientation block. Use when the user asks to create or update AGENTS.md. Write the draft into the file for in-file review; apply chat corrections to the file. Do not store product invariants inside this skill.
---

# Writing AGENTS.md

## Overview

`AGENTS.md` is the instruction file agents load on every turn. A skill loads only when the task matches it. The file holds rules an agent would break if they were not already in front of it. Procedures stay in skills.

This skill describes **how** to build and refresh that file. It does not freeze today's repository rules. Facts come from the current tree; planned direction comes from the user via `interview-me`.

## When to Use

- The user asks to create `AGENTS.md`
- The user asks to update the existing `AGENTS.md`

Do not add `CLAUDE.md`, a nested `AGENTS.md`, or a commit unless they ask for that too.

## Shape

- English
- Root `AGENTS.md` only, unless the user asks for another
- Human-readable first: dry, clear, no filler
- Headings, bullets, and tables when they help
- One rule per bullet
- A line stays only when deleting it would make an agent do the wrong thing
- No hard line or character budget; cut welcome text and repetition before adding length

A later service gets its own `AGENTS.md` only when its commands differ and the user asks for that file.

## Create workflow

1. **Build understanding from the repository.** Read what agents need to obey today: `README.md`, `pyproject.toml`, `.githooks/`, `.github/workflows/`, package layout, and `.agents/skills/git-workflow-and-versioning/SKILL.md`. Pull commands only from files that exist. Do not invent stacks or copy sample commands from unrelated skills.
2. **Interview for the future.** Open `interview-me` and push it as far as it goes. Ask what is planned conceptually that is not yet true in the tree. Stop only after that skill's confirmed statement of intent (explicit yes).
3. **Write the file.** Put the draft into root `AGENTS.md` so the user reviews it there, not as a long paste in chat. Structure:
   - **Current** — facts and rules verified against the repo now
   - **Future orientation** — short conceptual pointers from the interview
4. **Future block rules.** Orient the agent so it does not fight the planned direction. Do not treat those lines as a license to implement missing products, services, or migrations early.
5. **Apply corrections.** The user reads the file and sends edits in chat. Change the file; do not ask them to edit it by hand.
6. **Verify** with the checklist below. This skill's checklist is enough; do not open `verification-before-completion` unless the user asks for that separately.

## Update workflow

When `AGENTS.md` already exists:

1. Re-read the repository sources from the create workflow.
2. Diff the file against the tree:
   - Drop or rewrite bullets the code no longer supports
   - Move items from **Future orientation** into **Current** when they are now true in the repo
   - Remove future lines that the user has abandoned only when they say so, or when the interview replaces them
3. Full `interview-me` on future plans again only when:
   - the user asks to rebuild or rethink plans, or
   - the reconcile step finds gaps that cannot be closed from the repo alone
4. Write the updated file, apply chat corrections to the file, then run the checklist.

## What belongs in the file

- Commands agents must run, copied from real hook/CI/docs files
- Short pointers into skills when the full procedure lives there (especially `git-workflow-and-versioning`)
- Repo facts that fail the delete-test above
- A separate **Future orientation** section for confirmed conceptual plans

## Leave out of this skill

- A frozen list of product invariants for this repository
- Sample `npm` / `pnpm` commands from other ecosystems

## Leave out of AGENTS.md

- A welcome, a slogan, or a restatement of the README
- The skill catalog
- A `Co-Authored-By` trailer
- Linter and typechecker config that already lives in `pyproject.toml`
- Secret values and database URLs
- Implementation plans disguised as future orientation

## Interaction with Other Skills

- **`interview-me`**: required for future orientation on create, and on update when plans must be rebuilt or gaps need the user. Run it to completion.
- **`using-agent-skills`**: opens this skill when the task is the instruction file.
- **`git-workflow-and-versioning`**: branch naming, shared-branch freshness, and who creates the commit. Put only the short form into `AGENTS.md`; do not paste that skill.
- **`documentation-and-adrs`**: ADRs and the README stay in their own files. Link them from `AGENTS.md` when a pointer prevents a mistake.
- **`verification-before-completion`**: optional; not part of this workflow unless the user asks.

## Verification

- [ ] Current bullets match the repository as it is now
- [ ] Every command was copied from a file that exists
- [ ] Future orientation is clearly separate, short, and conceptual — not an implementation brief
- [ ] Items that became true in the repo were moved out of Future orientation
- [ ] The draft is in root `AGENTS.md` for in-file review
- [ ] Chat corrections were applied to the file
- [ ] No `CLAUDE.md`, nested `AGENTS.md`, or commit unless the user asked
