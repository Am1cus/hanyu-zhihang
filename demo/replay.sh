#!/usr/bin/env bash
# Non-destructive replay; the older filename remains as a compatibility wrapper.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/reset_and_replay.sh" "$@"
