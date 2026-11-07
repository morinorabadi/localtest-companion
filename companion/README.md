# Companion runtime

Start with the repository [README](../README.md) for two-machine installation and
[project configuration](../docs/PROJECTS.md) for startup commands and environments.

Installed copies of this guide may not include the full repository. The public
documentation is https://github.com/morinorabadi/localtest-companion#readme.

- `install.sh`: installs the companion and checksum-verified Mutagen.
- `update.sh`: updates the companion while preserving profiles, environments,
  and existing local app data.
- `localtest.py`: Ubuntu profiles, sync, app supervision, and action registration.
- `bridge_worker.py`: Ubuntu worker that connects outbound through SSH.
- `remote.py`: Coder-side request queue, CLI, and SSH broker.
- `AGENT_GUIDE.md`: runtime workflow and verification boundaries for agents.

Run behavior checks from the repository root:

```bash
python3 -m unittest discover -s companion -v
```
