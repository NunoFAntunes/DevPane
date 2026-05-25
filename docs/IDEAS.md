# DevPane — Improvement Ideas

A senior-dev audit of DevPane's current task / sprint / subtask model and
ideas for making it more useful for day-to-day developer workflows.

## Scoring

Each idea is rated on three 1–5 axes:

- **Usefulness** — how much it improves the daily developer workflow (5 = high impact).
- **Complexity** — implementation difficulty (5 = hard; touches storage, UI, IPC, threading).
- **Scope** — how far it strays from DevPane's "files-first drop-down notepad" charter (1 = perfectly on-mission, 5 = different product).

---

## A. Task model — fundamentals

### A1. Task priority / weight
Add `priority: low|med|high` (or numeric) to frontmatter. Sort tasks within a sprint by priority then date.
- Usefulness: 4 — universal, low friction.
- Complexity: 2 — frontmatter field + sort comparator + a small UI tag.
- Scope: 1 — natural extension of existing metadata.

### A2. Due dates / deadlines
Optional `due:` in frontmatter; render overdue / today / soon visually in the task list.
- Usefulness: 4
- Complexity: 2
- Scope: 1

### A3. Time estimate + actual
`estimate:` (e.g. `2h`) and `spent:` fields. Sprint header shows roll-up.
- Usefulness: 3 — useful for sprint planning, but few devs log honestly.
- Complexity: 2
- Scope: 2

### A4. Tags / labels ✅ shipped
`tags: bug, refactor` (comma-separated string) in frontmatter. Up to three
chips per row in the sidebar, single-tag filter dropdown in the footer.
- Usefulness: 5
- Complexity: 2
- Scope: 1

### A5. Status beyond "done" ✅ shipped
Boolean `done` replaced by `status: todo|doing|blocked|done`, surfaced as
a clickable pill on each task row. Sprint bar shows per-status counts.
Lazy migration: legacy `done:` is read with a fallback rule and rewritten
on next mutation.
- Usefulness: 4
- Complexity: 2 — migration of existing files needed.
- Scope: 1

### A6. Subtask notes (single-line)
Today subtasks are checkbox + text only. Allow an optional one-line note per subtask (already half-asked-for in `LIMITATIONS.md`).
- Usefulness: 3
- Complexity: 2 — JSON schema bump + small UI.
- Scope: 2 — explicitly out-of-scope today; revisit if users ask.

---

## B. Capture — making the drop-down stickier

### B1. Quick-add syntax in the editor
Type `[] buy milk` on a new line and on save it becomes a subtask. `#tag`, `!high`, `@2026-05-30` parsed inline.
- Usefulness: 5 — preserves the "one keystroke, type, gone" ethos.
- Complexity: 3 — parser + reconciliation with the structured subtask store.
- Scope: 1

### B2. Clipboard-aware capture
On open, if the clipboard contains a URL / code block / stack trace, offer "paste as new task" via a single shortcut.
- Usefulness: 3
- Complexity: 2
- Scope: 2

### B3. Snippet / template tasks
`devpane-toggle --template bug` opens with a pre-filled body (repro / expected / actual). Templates are just `.md` files in a `templates/` dir.
- Usefulness: 3
- Complexity: 1
- Scope: 1

### B4. Daily standup note
Auto-generated read-only view: tasks closed yesterday, doing today, blocked. Useful right before standup.
- Usefulness: 4
- Complexity: 2 — pure query over the index.
- Scope: 2

---

## C. Sprints — making them more than chronological buckets

### C1. Sprint goal + retro
A sprint can optionally have its own `.md` file (goal at top, retro at bottom). Shown when no task selected for that sprint.
- Usefulness: 4
- Complexity: 2
- Scope: 1

### C2. Sprint dates + auto-rollover
Sprints get optional `start` / `end` dates. On end-date, prompt: "carry over unfinished?" — bulk-move open tasks into the next sprint.
- Usefulness: 4
- Complexity: 3
- Scope: 2

### C3. Sprint velocity / burndown (text only)
Tiny ASCII chart in the sprint header: `▇▇▆▆▅▃▂` of remaining open subtasks/tasks per day. No graphics dependency.
- Usefulness: 3 — fun, helps personal pacing.
- Complexity: 3 — needs a per-day snapshot of counts.
- Scope: 3

### C4. Archive past sprints
Hide finished sprints behind a "show archive" toggle so `Alt+Left/Right` doesn't have to walk them.
- Usefulness: 3
- Complexity: 1
- Scope: 1

---

## D. Search, navigation, view

### D1. Command palette (`Ctrl+K`)
One overlay for: jump to task, jump to sprint, change status, add tag, run actions. Heavy lifting is just FTS5 + a small action registry.
- Usefulness: 5
- Complexity: 3
- Scope: 1

### D2. Saved filters / smart lists
`@blocked`, `@today`, `@untagged`, `tag:bug` as pinnable views in the task sidebar.
- Usefulness: 4
- Complexity: 3
- Scope: 2

### D3. Full-text result preview
Search hits show the line of context they matched. Already half-there with FTS5.
- Usefulness: 4
- Complexity: 2
- Scope: 1

### D4. Backlinks between tasks
`[[note-20260518-1430]]` syntax → on render, both ends see each other in a "linked" footer. Cheap if filenames are stable (they are — see `LIMITATIONS.md`).
- Usefulness: 4
- Complexity: 3
- Scope: 2 — pulls toward Obsidian territory; keep minimal.

---

## E. Developer integrations (where the real leverage is)

### E1. Git-aware task linking
Detect the current branch / repo in the focused window's CWD (best-effort) and offer "link this task to branch `feat/foo`". Store the branch name in frontmatter; clicking it copies `git checkout feat/foo`.
- Usefulness: 4
- Complexity: 3
- Scope: 3 — DevPane is intentionally not a git tool.

### E2. Commit-message helper
"Copy as commit" on a task → produces `type(scope): title` from frontmatter + the open subtasks as the body.
- Usefulness: 3
- Complexity: 1
- Scope: 2

### E3. Issue-tracker import
`devpane-toggle --import gh:owner/repo#123` fetches a GitHub / GitLab issue into a new task. Read-only sync — keep DevPane local-first.
- Usefulness: 4
- Complexity: 4 — auth, rate limits, mapping.
- Scope: 4 — meaningful surface-area increase.

### E4. CLI `devpane add "fix the foo" --sprint current --tag bug`
A real CLI surface (not just `--toggle`). Scriptable from shell hooks, `git post-commit`, etc.
- Usefulness: 5
- Complexity: 2 — IPC already exists; just expose commands.
- Scope: 1

### E5. Editor integration (VSCode / nvim)
A tiny extension that calls `devpane-toggle add-from-selection`. Highlight a TODO comment → push to DevPane.
- Usefulness: 4
- Complexity: 4 — separate codebase to maintain per editor.
- Scope: 4

---

## F. Persistence, sync, safety

### F1. Built-in `git` autosave
Detect that the notes dir is a git repo; on each debounce-flush, optional auto-commit. Off by default.
- Usefulness: 4 — kills the "last write wins" footgun in `LIMITATIONS.md`.
- Complexity: 3
- Scope: 2

### F2. Conflict markers on stale write
Watch the file on disk; if mtime changed since we last read, show a banner with diff instead of overwriting.
- Usefulness: 4
- Complexity: 4 — file watching + diff UX.
- Scope: 2

### F3. Encrypted notes dir option
Some devs paste credentials by accident. Provide a `--encrypted` mode backed by `age` / `gocryptfs`. Out of scope but worth flagging.
- Usefulness: 2
- Complexity: 5
- Scope: 5

### F4. Export to single-file markdown / PDF
"Export sprint" → one stitched markdown file. Useful for retros, handovers.
- Usefulness: 3
- Complexity: 2
- Scope: 2

---

## G. UX polish

### G1. Keyboard-only task ops
`n` new task, `d` toggle done, `x` delete, `1-3` priority, `/` search, `g s` go to sprint. Fully chord-able.
- Usefulness: 5
- Complexity: 2
- Scope: 1

### G2. Pomodoro / focus timer per task
Start timer on a task → time accumulates into `spent:`. Drop-down shows running timer in the title bar.
- Usefulness: 3
- Complexity: 3
- Scope: 3

### G3. Markdown render preview mode
Toggle (`Ctrl+E`?) between source and rendered. GtkSourceView + a libadwaita-styled web view or a markdown-to-pango renderer.
- Usefulness: 3
- Complexity: 3
- Scope: 2

### G4. Per-task colour / icon
A single emoji or colour swatch from the frontmatter shown in the sidebar — fast visual scanning.
- Usefulness: 3
- Complexity: 1
- Scope: 1

---

## H. Plugin surface (long-term)

### H1. Hook system on task/subtask events
`on_task_done`, `on_sprint_close` → run a user script. Cheap power-user lever.
- Usefulness: 3
- Complexity: 3
- Scope: 3

### H2. Read-only HTTP API on the IPC socket
Local-only JSON endpoint listing tasks/sprints. Lets a Polybar / Waybar widget show `3 open · 1 blocked`.
- Usefulness: 4
- Complexity: 3
- Scope: 3

---

## Suggested next batch

If picking a small, coherent v0.2 from this list:

1. **A4 Tags** + **A5 Status enum** — ✅ shipped (Unreleased).
2. **B1 Quick-add syntax** — preserves the drop-down ethos.
3. **D1 Command palette** + **G1 Keyboard ops** — make power-use feel native.
4. **E4 CLI surface** — unlocks shell / editor integrations without owning them.
5. **F1 Optional git autosave** — closes the biggest safety gap in `LIMITATIONS.md`.

Everything else is either nice-to-have or pulls DevPane toward being a
different product.
