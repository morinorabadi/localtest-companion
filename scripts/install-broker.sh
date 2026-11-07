#!/usr/bin/env bash
# Run inside the Coder workspace. This does not touch Ubuntu or app profiles.
set -euo pipefail
tool_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v python3 >/dev/null || { echo 'Python 3.10+ is required' >&2; exit 1; }
python3 - "$tool_root" "${LOCALTEST_INSTALL_PREFIX:-$HOME/.local}" <<'PY'
from pathlib import Path
import shlex
import sys
if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10+ is required')
root, prefix = map(lambda p: Path(p).expanduser().resolve(), sys.argv[1:])
broker = root / 'companion/remote.py'
if not broker.is_file():
    raise SystemExit('Cannot find companion/remote.py')
directory = prefix / 'bin'
directory.mkdir(parents=True, exist_ok=True)
wrapper = directory / 'localtest-remote'
wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(broker)) + ' "$@"\n')
wrapper.chmod(0o755)
print(f'Installed Coder CLI: {wrapper}')
print(f'Ubuntu bridge broker path: {broker}')
print('Keep the tool checkout here; rerun this installer if it moves.')
PY
