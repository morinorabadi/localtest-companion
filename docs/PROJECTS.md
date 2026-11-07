# Project configuration

## Paths and lifecycle

| Purpose | Default Ubuntu path |
| --- | --- |
| Profile | `~/.config/localtest/projects/NAME.json` |
| Local overrides | `~/.config/localtest/env/NAME/project.env` |
| Managed source mirror | `~/localtest/NAME` |
| Companion state | `~/.local/state/localtest/NAME` |

Profiles capture the terminal's PATH at registration. Select your Node/Python
runtime first. After replacing a runtime, update the profile's `path` and run
`localtest start NAME`. `localtest config NAME` prints the editable JSON path.
`LOCALTEST_CONFIG_DIR` and `LOCALTEST_STATE_DIR` can override the config/state roots.

Setup/start/stop commands execute with Bash in the local source mirror. The start
command must remain in the foreground so systemd can supervise it. `--setup` runs
before startup and again on root dependency-lock or `project.env` changes.
An explicitly supplied `--start` disables automatic dependency installation;
provide `--setup` if the app needs it.

## Python or a custom runtime

Run **on Ubuntu**, replacing example workspace/source values:

```bash
localtest add worker --workspace dev --remote /home/coder/worker --port 8000 \
  --setup 'python3 -m venv .venv && .venv/bin/pip install -r requirements.txt' \
  --start '.venv/bin/uvicorn app:app --host 127.0.0.1 --port "$PORT" --reload'
localtest start worker
```

Use `--restart-on-change` for an app without native reload. It watches the whole
source tree, waits for a quiet interval, then restarts the foreground command.
Ignored runtime/dependency/build directories do not trigger these restarts.
Dependency changes outside the root Node lockfiles need your own setup/watcher
or an explicit `localtest start NAME`.

## Docker Compose

Install Docker and verify `docker info` succeeds without sudo, including from
the systemd user service. Then register your app's existing Compose workflow:

```bash
localtest add stack --workspace dev --remote /home/coder/stack --port 8080 \
  --start 'docker compose up --build --watch' \
  --stop 'docker compose stop'
localtest start stack
```

This example requires a Compose file with a valid `develop.watch` configuration
and a web port mapped to the selected local port. `--port` does not rewrite your
Compose file. Alternatively, use `--restart-on-change` and a project wrapper that
rebuilds, migrates, starts containers, then stays in the foreground following logs.

Localtest exports `COMPOSE_PROJECT_NAME=localtest-NAME` for isolated normal Compose
networks/volumes. Fixed container names, explicit shared/external volumes, and
hardcoded published host ports still need application-specific isolation.
Bind local services to loopback. Set each service's port independently: generic
profiles export frontend `PORT`, which must not accidentally become the API port.

Cloud `.env` files are excluded. Configure local env files explicitly and keep
them outside the managed mirror. Some confined Docker installations cannot read
hidden config directories such as `~/.config`: have your project wrapper stage
private, mode-600 runtime copies under `~/localtest-runtime/NAME/env/`, outside
the mirror. Do not fix access by making secrets world-readable.

## Environment values

`project.env` accepts simple `KEY=value` lines and optional single/double quotes.
It does not execute shell syntax, interpolate `$VARIABLES`, or run `$(commands)`.
Treat values as literal data. This file augments the app and action environment;
other env files require explicit loading by your app/start command.

Use extra `--ignore PATTERN` flags for secret files, local databases, exports,
and generated files that are not already excluded. `.env.example` files are
synced by default, so examples must never contain actual secrets.

## Named actions

Register **on Ubuntu**, then refresh bridge capabilities:

```bash
localtest action myapp test-api --cwd server --command 'npm test -- "$@"'
localtest action myapp health --command 'curl --fail --silent --show-error "http://127.0.0.1:$PORT/health"'
localtest bridge enable myapp --broker /home/coder/localtest-companion/companion/remote.py
```

Run **inside Coder**:

```bash
localtest-remote status myapp
localtest-remote run --timeout 900 myapp test-api --runInBand
localtest-remote run myapp health
```

The registration command is trusted local shell code. Request arguments are
passed as literal positional values, not interpolated into that code. Never
add `eval "$*"` or an equivalent arbitrary-shell action. Working directories
must stay inside the project mirror. Actions run serially per profile, with a
maximum 1800-second timeout and the last 128 KiB of output returned.

## Update an installation

On Ubuntu, update the tool checkout (separate from the managed app mirror):

```bash
cd ~/src/localtest-companion
git pull --ff-only
bash companion/update.sh
localtest start myapp
localtest bridge enable myapp --broker /home/coder/localtest-companion/companion/remote.py
```

The updater replaces program files without deleting profiles, environment values,
or application data. Restart each desired profile/bridge to load the new code.
Update the separate Coder tool checkout too, then rerun `scripts/install-broker.sh`
if its location changed. Review updates to this trusted local execution tool.
