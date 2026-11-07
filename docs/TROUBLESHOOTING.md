# Troubleshooting

Start with `localtest doctor` and `localtest status` **on Ubuntu**. The doctor
lists tools, not HTTP readiness. Only the runtimes used by your app are needed.

## SSH or initial sync fails

On Ubuntu, run `coder list`, `coder config-ssh --yes`, and
`ssh -o ConnectTimeout=60 YOUR-WORKSPACE.coder true`. If the generated alias is
different, pass `--host` at registration or update `host` in the existing profile.
Reauthenticate with `coder login` if credentials expired. Fix SSH before sync.

The initial sync requires a reachable workspace. Later starts can use previously
synced code during an outage; Mutagen reconnects when connectivity returns.
The shared daemon sets `MUTAGEN_SSH_CONNECT_TIMEOUT=60` for Coder tunnels.

## Service is active but the app is unavailable

Inspect bounded logs on Ubuntu:

```bash
journalctl --user -u localtest-myapp.service -n 100 --no-pager --all --output=cat
localtest run myapp health
```

Dependency installation/builds may still be running. Check actual HTTP readiness
and whether the app honors the configured port. Nested dependency lockfiles are
not installed automatically by the generic Node profile; use a custom setup.
`localtest start myapp` reruns setup and restarts the service.

## Agent says the bridge is offline

On Ubuntu:

```bash
localtest bridge enable myapp --broker /home/coder/localtest-companion/companion/remote.py
localtest bridge status myapp
journalctl --user -u localtest-bridge-myapp.service -n 80 --no-pager --all --output=cat
```

The broker path must exist **inside Coder** and be readable with Python available
there. Verify the same profile name, SSH alias, and broker path on both sides.
Check `localtest-remote status myapp` in Coder afterward. Do not send a request
to a different person's profile or assume an offline request was queued.

## An action is unavailable

Register it with `localtest action` on Ubuntu, then rerun `localtest bridge enable
myapp`. Capabilities refresh on reconnect. `status` and `journal` are the only
built-in actions; app health and tests need explicit registration.

## Docker permission or environment errors

Check `docker info` without sudo. After adding your user to a Docker-access group,
log out/back in so the systemd user manager receives the new group membership.
Confined Docker can also refuse files under hidden `~/.config` directories;
see [private runtime copies](PROJECTS.md#docker-compose). Keep mode-600 secrets.
Do not copy cloud env files into Ubuntu or expose credentials in diagnostic logs.

## A request was interrupted

Retrieve `localtest-remote result JOB_ID` in Coder and inspect app state. The
action may have changed data before disconnecting. Its outcome is unknown; it
is deliberately not replayed. Cancel only a still-pending request with
`localtest-remote cancel JOB_ID`. See `companion/AGENT_GUIDE.md` for queue rules.

## systemd user services are unavailable

Use an Ubuntu login session with a working user manager. On Windows, follow the
[WSL 2 systemd setup](WINDOWS.md#2-check-systemd-inside-ubuntu). A minimal
container or shell without systemd is not an Ubuntu runtime target for this tool.
Optional `sudo loginctl enable-linger "$USER"` enables startup before login;
it does not install systemd, start WSL at Windows login, or keep WSL alive.
