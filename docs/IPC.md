# DevPane — IPC Protocol

The daemon (`devpaned`) exposes a Unix domain socket at
`$XDG_RUNTIME_DIR/devpane/devpane.sock` (permissions `0600`, owner-only). The
CLI client (`devpane-toggle`) and any third-party scripts speak a trivial
line-delimited JSON protocol over it.

## Connection model

One command per connection:

1. Client opens the socket.
2. Client writes **one JSON object + `\n`**.
3. Server writes **one JSON object + `\n`**.
4. Both sides close.

There is no streaming, no multiplexing, no keep-alive. Each toggle press is
a fresh connection. This keeps the CLI to ~20 lines and makes the server
trivially reentrant.

## Request format

```json
{ "cmd": "<command>", ... }
```

The `cmd` field is required and must be a string. Additional command-specific
keys are accepted (none of the M2 commands use them yet).

## Response format

```json
{ "ok": true, "data": { ... } }
```

or

```json
{ "ok": false, "error": "<message>" }
```

Both clients and servers ignore unknown fields, so the protocol is
forward-compatible.

## Commands (M2)

| `cmd` | Effect | `data` on success |
|-------|--------|-------------------|
| `toggle` | Flip the visibility flag (M3+ flips the window). | `{"visible": bool}` |
| `show` | Force visible. | `{"visible": true}` |
| `hide` | Force hidden. | `{"visible": false}` |
| `status` | Report daemon state. | `{"version", "visible", "notes", "pid", "socket"}` |
| `quit` | Stop the daemon cleanly. | `{}` |

## Error responses

The server returns `{"ok": false, "error": "..."}` for:

- `invalid json: ...` — request was not valid JSON.
- `payload must be a JSON object` — top-level array, string, etc.
- `missing 'cmd' string` — no `cmd` field or wrong type.
- `unknown command: <cmd>` — not in the dispatch table.
- `handler error: <message>` — handler raised an exception.

## Single-instance behaviour

The daemon takes an `fcntl.flock` on
`$XDG_RUNTIME_DIR/devpane/devpane.pid`. If a second `devpaned` is launched:

1. The new process fails to acquire the lock.
2. It probes the socket; if a peer answers, it forwards a `toggle` and exits
   with status 0.
3. If the lock is held but the socket isn't responsive (split state), the
   new process exits with status 1 and an error log.

This lets users bind either `devpaned` *or* `devpane-toggle` to a hotkey —
both produce a toggle.

## Inspection from the shell

```sh
echo '{"cmd":"status"}' | socat - "UNIX-CONNECT:$XDG_RUNTIME_DIR/devpane/devpane.sock"
```

Or, more simply:

```sh
devpane-toggle status --json
```

## Why asyncio (M2), and the M3 bridge

The M2 daemon runs an `asyncio` event loop because there's no GTK yet. M3
introduces a GLib main loop for the GTK window. The two loops will be
bridged by:

- Running the asyncio event loop on a dedicated background thread.
- Posting command-handler effects to the GLib main thread with
  `GLib.idle_add` whenever they need to touch the window.

The wire protocol does not change.
