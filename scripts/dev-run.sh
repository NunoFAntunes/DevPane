#!/usr/bin/env bash
# Run devpaned from source with verbose logging.
set -euo pipefail

cd "$(dirname "$0")/.."

export G_MESSAGES_DEBUG="${G_MESSAGES_DEBUG:-devpane}"
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m devpane "$@"
