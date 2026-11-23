#!/bin/zsh
set -eu
cd -- "${0:A:h}"
release=Phase4/releases/energy_residual_lstm_v3_rc1
if [[ -d lstm-wheelhouse ]]; then
  if [[ ! -x .lstm-venv/bin/python ]]; then
    interpreter=python3.12
    [[ -x .competition-venv/bin/python ]] && interpreter=.competition-venv/bin/python
    "$interpreter" -m venv .lstm-venv
  fi
  interpreter=.lstm-venv/bin/python
  "$interpreter" -m pip install --disable-pip-version-check --no-index --find-links lstm-wheelhouse 'numpy==2.0.2' 'torch==2.8.0' >&2
else
  interpreter=.venv/bin/python
fi
exec "$interpreter" "$release/runtime.py" --request "${1:-$release/example_request.json}"
