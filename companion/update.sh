#!/usr/bin/env bash
# Update an existing installation without downloading runtimes or restarting the app.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 - "$HERE" <<'PY'
import ast, os, shutil, sys, tempfile
from pathlib import Path
source=Path(sys.argv[1])
prefix=Path(os.environ.get('LOCALTEST_INSTALL_PREFIX', str(Path.home()/'.local'))).expanduser()
target=prefix/'share/localtest'
if not (target/'localtest.py').exists():
    raise SystemExit('No existing installation found; run install.sh instead.')
files=('localtest.py','remote.py','bridge_worker.py','README.md','AGENT_GUIDE.md')
for name in files:
    if name.endswith('.py'): ast.parse((source/name).read_text())
for name in files:
    fd, temporary=tempfile.mkstemp(prefix='.update-',dir=target)
    os.close(fd)
    shutil.copyfile(source/name,temporary)
    os.chmod(temporary,0o644)
    os.replace(temporary,target/name)
print('Companion updated. Profiles, environments, app processes and database volumes preserved.')
PY
