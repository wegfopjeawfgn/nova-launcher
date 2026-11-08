#!/usr/bin/env bash
set -euo pipefail
app_dir="$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/../share/nova-launcher"
export PYTHONPATH="$app_dir/vendor"
exec /usr/bin/python3 -B "$app_dir/nova.py" "$@"
