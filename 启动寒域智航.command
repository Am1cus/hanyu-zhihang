#!/bin/zsh
hyzh_repository="$(cd -- "$(dirname -- "$0")" && pwd)"
exec /bin/zsh "$hyzh_repository/competition/v2/start_v2.command" "$@"
