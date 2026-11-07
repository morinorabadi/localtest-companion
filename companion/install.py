#!/usr/bin/env python3
"""Install only the Ubuntu companion and its private, verified Mutagen binary."""
import hashlib
import io
import argparse
from pathlib import Path
import platform
import shlex
import shutil
import tarfile
import urllib.request

VERSION = "0.18.1"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
args = parser.parse_args()
if platform.system() != "Linux":
    raise SystemExit("Run this installer in Linux with systemd. On Windows, use Ubuntu in WSL 2; see docs/WINDOWS.md.")
arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
if not arch:
    raise SystemExit("Supported architectures: x86_64 and aarch64.")
base = args.prefix.expanduser().resolve() / "share/localtest"
binary_dir = base / "bin"
binary_dir.mkdir(parents=True, exist_ok=True)
asset = f"mutagen_linux_{arch}_v{VERSION}.tar.gz"
url = f"https://github.com/mutagen-io/mutagen/releases/download/v{VERSION}/"
print(f"Downloading Mutagen {VERSION} ({arch}) and verifying SHA-256...", flush=True)
with urllib.request.urlopen(url + "SHA256SUMS", timeout=60) as response:
    checksums = response.read().decode()
expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip("*") == asset)
with urllib.request.urlopen(url + asset, timeout=120) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit("Mutagen checksum mismatch; installation stopped.")
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
    for name in ("mutagen", "mutagen-agents.tar.gz"):
        source = archive.extractfile(name)
        if source is None:
            raise SystemExit("Missing archive member: " + name)
        (binary_dir / name).write_bytes(source.read())
        (binary_dir / name).chmod(0o755 if name == "mutagen" else 0o644)
for filename in ("localtest.py", "README.md", "AGENT_GUIDE.md", "remote.py", "bridge_worker.py"):
    shutil.copyfile(Path(__file__).with_name(filename), base / filename)
wrapper_dir = args.prefix.expanduser().resolve() / "bin"
wrapper_dir.mkdir(parents=True, exist_ok=True)
wrapper = wrapper_dir / "localtest"
wrapper.write_text("#!/bin/sh\nexport PATH=" + shlex.quote(str(binary_dir)) + ':"$PATH"\nexec python3 ' + shlex.quote(str(base / "localtest.py")) + ' "$@"\n')
wrapper.chmod(0o755)
print(f"Installed: {wrapper}\nRun: {wrapper} doctor\nExisting project configurations were preserved.")
