# DevPane

Linux drop-down notetaking pane for developers. Press a key, type, press the
key again — your notes are saved as plain markdown.

Each note is also a **task**: it gets a title, a done state, and an
ordered list of **subtasks** (checkbox + text) shown in a middle pane
between the task list and the editor. Tasks are grouped into **sprints**
(chronological, emergent from frontmatter) and navigable with
`Alt+Left` / `Alt+Right`.

**Status:** alpha `v0.1.0` shipped (M0–M8 done); the task / sprint /
subtask UI is on `main` as `Unreleased`. Packaging files (Arch PKGBUILD,
Flatpak manifest, systemd unit) are in [`packaging/`](packaging/) but
not yet published to AUR / Flathub. See
[Overview](docs/OVERVIEW.md#project-status) for the milestone matrix and
[CHANGELOG](CHANGELOG.md) for release notes.

## Docs

- [Overview](docs/OVERVIEW.md) — what DevPane is, why, and current status
- [Architecture](docs/ARCHITECTURE.md) — runtime design and module layout
- [Storage](docs/STORAGE.md) — on-disk layout, name rules, inspection commands
- [IPC](docs/IPC.md) — wire protocol between `devpane-toggle` and `devpaned`
- [GUI](docs/GUI.md) — GTK window, threading model, mode selection, editor + polish
- [Limitations](docs/LIMITATIONS.md) — what DevPane doesn't do (yet) and the workarounds
- [Plan](docs/PLAN.md) — milestones and verification steps
- [Hotkey setup](docs/HOTKEY-SETUP.md) — per-DE binding instructions
- [Contributing](docs/CONTRIBUTING.md) — dev setup, tests, conventions
- [Changelog](CHANGELOG.md) — release notes

## Quick start (once implemented)

```sh
pipx install devpane
devpaned &                       # start the daemon
# then bind devpane-toggle to F12 in your DE — see docs/HOTKEY-SETUP.md
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
