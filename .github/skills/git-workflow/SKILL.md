---
name: git-workflow
description: Follow Tank's git branching, worktree, commit message, and PR conventions. Activate when creating branches, setting up worktrees, writing commit messages, opening PRs, or managing multi-phase feature work.
license: MIT
---

# Git Workflow Guidelines for Tank

## Branch Strategy

Tank uses a **linear phase-based branching model**. Each phase builds on the previous:

```
main (stable, tagged releases)
 └── phase1   (Core AI: agents, tools, memory, LLM)
      └── phase2  (Web: ASGI, SSE streaming, demo)
           └── phase3  (Advanced: parallel tools, self-correction)
                └── phase4  (Memory: RAG, persistence)
                     └── feature/<name>  (one-off features)
```

**Rules**:
- Never branch off `main` for feature work — branch from the latest phase.
- `main` only receives PRs from the latest stable phase or hotfix branches.
- `hotfix/<name>` branches from `main` and merges back to both `main` and current phase.

---

## Git Worktrees (Required for Phase Work)

Tank uses **git worktrees** so multiple phases can coexist on disk without checkout switching. Always set up a new worktree for each phase:

```bash
# Create phase branch and its worktree
git branch phase3 phase2
git worktree add C:/path/to/tank/worktrees/phase3 phase3

# List all active worktrees
git worktree list

# Remove when work is merged (don't leave stale worktrees)
git worktree remove worktrees/phase3
```

**Directory convention**:
```
tank/
├── worktrees/
│   ├── phase1/    ← git worktree for phase1 branch
│   ├── phase2/    ← git worktree for phase2 branch
│   └── phase3/    ← git worktree for phase3 branch
```

**Important**: The `worktrees/` directory is **not** gitignored at the repo root — each worktree is managed by git internally. Never manually delete worktree directories.

---

## Commit Message Format

Follow **Conventional Commits** (https://conventionalcommits.org):

```
<type>(<scope>): <short summary in imperative mood>

[optional body: what and why, not how]

[optional footer: breaking changes, issue refs]
```

### Types

| Type | Use for |
|---|---|
| `feat` | New feature (agent route, SSE event type, new tool capability) |
| `fix` | Bug fix (error in streaming, memory leak, wrong schema) |
| `refactor` | Code restructuring without behaviour change |
| `test` | Adding or updating tests only |
| `docs` | README, docstrings, CHANGELOG updates |
| `chore` | Build config, pyproject.toml, CI workflows |
| `perf` | Performance improvement (e.g., concurrent execution) |

### Scopes

Use the Tank module name as scope: `agent`, `llm`, `tools`, `memory`, `routing`, `response`, `app`, `example`, `tests`.

### Examples

```
feat(agent): implement concurrent tool execution with asyncio.gather

fix(tools): preserve Field description when param has default value

refactor(llm): extract provider-specific message formatting to helpers

test(routing): add SSE event sequence validation for /chat endpoint

docs(tools): add Google-style docstring parsing examples to SKILL.md

chore(ci): add pytest asyncio mode=strict to pyproject.toml
```

### Rules
- Summary line ≤ 72 characters.
- Imperative mood: "add", "fix", "implement" — not "added", "fixes", "implementing".
- No period at the end of the summary line.
- Body explains **why**, not what the diff shows.

---

## Commit Hygiene

- **One logical change per commit** — don't bundle unrelated fixes.
- **Stage intentionally**: use `git add <file>` not `git add .` when including unrelated changed files.
- **Never commit**:
  - `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/` (covered by `.gitignore`)
  - API keys or secrets
  - Unfinished WIP code (use `git stash` instead)

---

## Pull Request Conventions

### Title
Match the primary commit message format:
```
feat(agent): Phase 2 – ASGI/Web Core, SSE Streaming, and Demo Integration
```

### Body Template

```markdown
## Summary
Brief description of what this PR implements and why.

## Changes
- `tank/core/app.py`: Implemented `Tank` class wrapping Starlette with `@agent_route`
- `tank/core/response.py`: `AgentStreamResponse` for SSE formatting
- `tests/test_routes.py`: Route registration and SSE stream validation tests

## Testing
- [ ] All existing tests pass: `pytest` → N passed
- [ ] New tests added for new functionality
- [ ] Manual verification: describe what was tested manually

## Notes / Breaking Changes
List any breaking changes or migration notes here.
```

### PR Rules
- PRs must target the **parent phase branch**, not `main` (unless it's a final phase release).
- Every PR must include tests for changed behaviour.
- Use `gh pr create --base phase2 --head phase3` — never rely on GitHub UI defaults.
- Link to relevant issues or implementation plan documents in the PR body.

---

## Phase Release Checklist

Before opening a PR from a phase branch to `main`:

- [ ] All tests pass (`pytest` — zero failures)
- [ ] `CHANGELOG.md` updated with phase summary
- [ ] `pyproject.toml` version bumped (`0.1.0` → `0.2.0` per phase)
- [ ] No `TODO` or `FIXME` comments left in changed files
- [ ] No debug `print()` statements in production code
- [ ] Worktree directory cleaned up after merge

---

## Useful Commands

```bash
# Create and switch to a new phase worktree
git branch phase3 phase2 && git worktree add ./worktrees/phase3 phase3

# Commit all changes with conventional message
git add tank/ai/tools.py tank/ai/agents.py tests/test_advanced_tools.py
git commit -m "feat(tools): parse Google/Sphinx docstrings into Pydantic Field descriptions"

# Push and create PR in one step
git push origin phase3
gh pr create --title "Phase 3: Advanced Tool Calling & Agent Self-Correction" \
             --base main --head phase3

# View all worktrees
git worktree list

# Clean up merged worktree
git worktree remove worktrees/phase3
git branch -d phase3
```
