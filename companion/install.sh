#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v python3 >/dev/null || { echo 'Install Python: sudo apt install python3'; exit 1; }
python3 "$HERE/install.py" "$@"
