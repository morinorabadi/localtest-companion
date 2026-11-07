# Localtest companion

Edit in a Coder workspace. Run the app locally on Ubuntu, including Ubuntu in
WSL 2 on Windows. Let your coding agent check its logs, health, and tests through
an outbound command bridge.

**Using Windows?** Start with the [Windows / WSL 2 guide](docs/WINDOWS.md), then
run the Ubuntu commands below inside that WSL distribution. The companion uses
Linux systemd services; it does not install as a native Windows service.

Localtest uses Mutagen for one-way source sync and systemd user services to
supervise each local app. It supports Node/Next/Vite projects automatically and
other stacks through explicit setup/start/stop commands. No commits, public
Ubuntu address, or inbound port forwarding are needed for the workflow.

**Setting up with an agent?** Give it [this setup prompt](docs/AGENT_SETUP.md).
The repository's [AGENTS.md](AGENTS.md) explains how to complete and verify setup
without confusing Coder's localhost with Ubuntu's.

## What runs where

| Coder workspace | Ubuntu or Ubuntu in Windows WSL 2 |
| --- | --- |
| Authoritative source checkout and coding agent | Synced source mirror and app runtimes |
| Python command broker and private request queue | Local environment files, databases, and user services |
| `localtest-remote` sends named requests | `localtest` manages profiles, sync, and the outbound bridge |

Each coworker uses their own Coder access, Ubuntu profile, environment, and data.
Sharing this repository does not share your app's source or credentials.
On Windows, the Ubuntu profile, credentials, and app live inside WSL; the browser
can remain a Windows application.

## 1. Prepare Coder

Run **inside the Coder workspace**. Clone this tool separately from your app:

```bash
git clone https://github.com/morinorabadi/localtest-companion.git /home/coder/localtest-companion
cd /home/coder/localtest-companion
bash scripts/install-broker.sh
export PATH="$HOME/.local/bin:$PATH"
python3 -m unittest discover -s companion -v
```

The broker needs Python 3.10+ on Linux. It starts on demand through SSH; it does
not open a network listener. Keep this checkout at its installed path.

## 2. Prepare Ubuntu

Windows users: complete [WSL prerequisites](docs/WINDOWS.md) first. All Ubuntu
commands in this repository also mean **inside Ubuntu in WSL 2** on Windows.

Requirements: Python 3.10+, Git, OpenSSH client, working systemd user services,
and the [Coder CLI](https://coder.com/docs/install). Install your application's
Node/Python/Docker runtimes separately. The installer adds a private,
checksum-verified Mutagen 0.18.1 binary for Linux amd64 or arm64.

Run **on Ubuntu**:

```bash
sudo apt update
sudo apt install -y python3 git openssh-client
git clone https://github.com/morinorabadi/localtest-companion.git ~/src/localtest-companion
cd ~/src/localtest-companion
bash companion/install.sh
export PATH="$HOME/.local/bin:$PATH"
localtest doctor
```

Authenticate to **your own** Coder deployment and generate SSH configuration:

```bash
coder login https://YOUR-CODER-DEPLOYMENT
coder config-ssh --yes
coder list
ssh YOUR-WORKSPACE.coder true
```

Select the actual workspace name and SSH alias from that configuration. Below,
`dev` is an example workspace and `/home/coder/myapp` is an example app checkout.

## 3. Register your app on Ubuntu

For a Node/Next/Vite app with a root npm or pnpm lockfile, first select the Node
version/package manager required by that project, then run:

```bash
localtest add myapp --workspace dev --remote /home/coder/myapp --port 3000
localtest start myapp
localtest logs myapp
```

Open http://localhost:3000 **on Ubuntu** after logs show the app is listening.
An omitted port is assigned from the unused profile ports starting at 3000.
Use `--host YOUR-SSH-ALIAS` if it differs from `WORKSPACE.coder`.

The root package must use `package-lock.json` or `pnpm-lock.yaml`. Next/Vite
receive explicit loopback/port flags; other packages run their `dev` script,
which must honor `PORT`. Use [custom commands](docs/PROJECTS.md) for monorepos,
Python, containers, or different package managers.

## 4. Give your agent access to results

Run **on Ubuntu**, using the actual broker checkout path inside Coder:

```bash
localtest action myapp health --command 'curl --fail --silent --show-error "http://127.0.0.1:$PORT/"'
localtest action myapp test --command 'npm test -- "$@"'
localtest bridge enable myapp --broker /home/coder/localtest-companion/companion/remote.py
```

Choose actions that match your app. For example, use `--cwd server` for a
subdirectory test suite. A health action should probe a real readiness endpoint
when your app has one. Named commands run with your Ubuntu user permissions.

Your agent can now run **inside Coder**:

```bash
localtest-remote status myapp
localtest-remote run myapp status
localtest-remote run myapp journal 80
localtest-remote run myapp health
localtest-remote run --timeout 900 myapp test
```

The bridge is independent of the app, so logs remain available when startup
fails. Only `status`, `journal`, and actions registered on Ubuntu are available.
There is no arbitrary remote-shell action.

## Verify the whole path before using your app

The included [Python smoke example](examples/python-http/README.md) needs no app
dependencies. It verifies source sync, Ubuntu HTTP readiness, and an agent bridge
round trip. Run it first if you want to separate infrastructure setup from your
application's dependencies.

## Daily use

Run these **on Ubuntu**:

```bash
localtest status
localtest sync-status myapp
localtest logs myapp
localtest stop myapp
localtest start myapp
localtest config myapp
```

`start` restarts a running profile and enables it at login. `stop` disables its
app service and pauses sync, preserving local data. Disable the independent
bridge separately with `localtest bridge disable myapp`. For startup before
login after a reboot, optionally run `sudo loginctl enable-linger "$USER"`.

Source sync is **one-way replica**: Coder is authoritative. Editing the Ubuntu
mirror can lose changes. Git metadata, `.env*` (except examples), dependencies,
and build output are excluded; custom secret paths require explicit ignores.
Keep local secrets and data outside the synced mirror.

Application health and tests need explicit checks. An active service, a source
save, or a successful Coder-side test does not prove the Ubuntu app is healthy.

## Further documentation

- [Agent setup prompt and completion checklist](docs/AGENT_SETUP.md)
- [Windows / WSL 2 setup and lifecycle](docs/WINDOWS.md)
- [Agent workflow and verification rules](companion/AGENT_GUIDE.md)
- [Project commands, environment files, Docker, and updates](docs/PROJECTS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Trust boundaries and privacy](SECURITY.md)
- [Contributing and tests](CONTRIBUTING.md)

MIT licensed. Source sync is powered by [Mutagen](https://mutagen.io/); workspace
connectivity is provided by [Coder](https://coder.com/). This is an independent
companion, not an official Coder or Mutagen product.
