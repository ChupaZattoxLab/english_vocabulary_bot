# Third-party agent skills

When two skills disagree, follow this order: rules written for this
repository, including `git-workflow-and-versioning`, then Addy Osmani's
skills, then the other packs.

The files under `.agents/skills/` are copies of MIT-licensed agent skills.
Each checklist sits in the skill folder that opens it. Paths inside the
skills were updated to match. `git-workflow-and-versioning` is adapted
for this repository: one branch holds the complete solution for one task
(`SCRUM-<number>/<english-slug>`, for example `SCRUM-32/add-ai-instructions`; several people may share it, and before editing it is updated together with `main` so the two do not conflict), review the diff and run this
repo's checks before a commit, and keep semantic versions for the day a
website or another service has an outside consumer. `incremental-implementation` points at
that rule and waits for the user before creating the commit. Skills that
hand work to another skill in this pack now say so under
`Interaction with Other Skills`. `systematic-debugging` calls
`verification-before-completion` by that name. The other procedures are
unchanged.

Copyright and source for each copy are listed below. The skills are MIT.

## Addy Osmani — agent-skills

Copyright (c) 2025 Addy Osmani

- Source: https://github.com/addyosmani/agent-skills

Skills:

- `skills/api-and-interface-design`
- `skills/browser-testing-with-devtools`
- `skills/ci-cd-and-automation`
- `skills/code-review-and-quality`
- `skills/code-simplification`
- `skills/context-engineering`
- `skills/debugging-and-error-recovery`
- `skills/deprecation-and-migration`
- `skills/documentation-and-adrs`
- `skills/doubt-driven-development` (includes `references/orchestration-patterns.md`)
- `skills/frontend-ui-engineering` (includes `references/accessibility-checklist.md`)
- `skills/git-workflow-and-versioning` (adapted for this repository)
- `skills/idea-refine` (includes `references/examples.md`, `references/frameworks.md`, `references/refinement-criteria.md`, `references/idea-refine.sh`)
- `skills/incremental-implementation`
- `skills/interview-me`
- `skills/observability-and-instrumentation` (includes `references/observability-checklist.md`)
- `skills/performance-optimization` (includes `references/optimization-patterns.md` and `references/performance-checklist.md`)
- `skills/planning-and-task-breakdown` (includes `references/definition-of-done.md`)
- `skills/security-and-hardening` (includes `references/hardening-patterns.md` and `references/security-checklist.md`)
- `skills/source-driven-development`
- `skills/spec-driven-development`
- `skills/test-driven-development` (includes `references/testing-patterns.md` and `references/writing-good-tests.md`)

## Jesse Vincent — superpowers

Copyright (c) 2025 Jesse Vincent

- Source: https://github.com/obra/superpowers

Skills:

- `skills/systematic-debugging` (includes `references/root-cause-tracing.md`, `references/defense-in-depth.md`, `references/condition-based-waiting.md`, `references/condition-based-waiting-example.ts`, `references/find-polluter.sh`)
- `skills/receiving-code-review`
- `skills/verification-before-completion`

`writing-good-tests.md` from this pack now lives at `skills/test-driven-development/references/writing-good-tests.md`. The rest of that skill repeated the Osmani test loop and is not included. `systematic-debugging` points at `test-driven-development`.

`CREATION-LOG.md` and the `test-*.md` files from `systematic-debugging` are not included. They test the skill text itself and are not part of the debugging procedure.

## Jeffallan — claude-skills

Copyright (c) 2025

- Source: https://github.com/Jeffallan/claude-skills (`skills/microservices-architect`)

Skills:

- `skills/microservices-architect` (includes `references/communication.md`, `references/data.md`, `references/decomposition.md`, `references/observability.md`, `references/patterns.md`)

The frontmatter names `devops-engineer`, `kubernetes-specialist`, `graphql-architect`, `architecture-designer`, and `monitoring-expert`. Those skills are not in this copy.

## Claude Skills Maintainers — claude-skills

Copyright (c) 2025 Claude Skills Maintainers

- Source: https://github.com/secondsky/claude-skills (`plugins/ml-model-training`)

Skills:

- `skills/ml-model-training` (includes `references/pytorch-training.md` and `references/tensorflow-keras.md`)
