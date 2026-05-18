# DevPane

Linux drop-down notetaking pane for developers. Press a key, type, press the
key again — your notes are saved as plain markdown.

**Status:** pre-alpha. M0–M6 complete (skeleton, storage, IPC daemon,
GTK window, platform adapters, markdown editor, polish); see
[Overview](docs/OVERVIEW.md#project-status) for the milestone matrix.
**Functionally usable.** Distribution (Flatpak, AUR) is next.

## Docs

- [Overview](docs/OVERVIEW.md) — what DevPane is, why, and current status
- [Architecture](docs/ARCHITECTURE.md) — runtime design and module layout
- [Storage](docs/STORAGE.md) — on-disk layout, name rules, inspection commands
- [IPC](docs/IPC.md) — wire protocol between `devpane-toggle` and `devpaned`
- [GUI](docs/GUI.md) — GTK window, threading model, mode selection
- [Plan](docs/PLAN.md) — milestones and verification steps
- [Hotkey setup](docs/HOTKEY-SETUP.md) — per-DE binding instructions
- [Contributing](docs/CONTRIBUTING.md) — dev setup, tests, conventions

## Quick start (once implemented)

```sh
pipx install devpane
devpaned &                       # start the daemon
# then bind devpane-toggle to F12 in your DE — see docs/HOTKEY-SETUP.md
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
