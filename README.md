# DevPane

Linux drop-down notetaking pane for developers. Press a key, type, press the
key again — your notes are saved as plain markdown.

**Status:** pre-alpha (M0 skeleton).

## Docs

- [Overview](docs/OVERVIEW.md) — what DevPane is and why
- [Architecture](docs/ARCHITECTURE.md) — runtime design and module layout
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
