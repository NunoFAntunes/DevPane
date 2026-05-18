#!/usr/bin/env bash
# Wipe DevPane local state (notes and index). Destructive — confirms first.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/devpane"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/devpane"

if [[ ! -e "$DATA_DIR" && ! -e "$STATE_DIR" ]]; then
    echo "Nothing to reset."
    exit 0
fi

echo "About to remove:"
[[ -e "$DATA_DIR" ]] && echo "  $DATA_DIR"
[[ -e "$STATE_DIR" ]] && echo "  $STATE_DIR"

read -r -p "Proceed? [y/N] " reply
case "$reply" in
    [yY]|[yY][eE][sS])
        rm -rf -- "$DATA_DIR" "$STATE_DIR"
        echo "Removed."
        ;;
    *)
        echo "Aborted."
        exit 1
        ;;
esac
