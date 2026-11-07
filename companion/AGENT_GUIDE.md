# Agent workflow: Coder edits, Ubuntu execution

Localtest has two machines. The Coder checkout is the authoritative source.
Ubuntu holds a one-way mirror, app processes, private environment, and local
database/object-store state. Each profile registers its own source and mirror;
other directories or external Git worktrees are not automatically synchronized.

On Windows, the Ubuntu runtime is inside WSL 2. Read `docs/WINDOWS.md` in the
repository before setup. Run the Linux companion, Coder CLI, SSH, and application
runtimes in that distro, with working systemd user services. Keep mirrors under
the Linux home directory. Windows browser reachability is a separate check from
the WSL HTTP probe, and WSL session/boot behavior differs from native Ubuntu.

## Discover the user's registration

On Ubuntu, `localtest status`, `localtest config NAME`, and `localtest sync-status
NAME` identify the registered project. Profiles live in
`~/.config/localtest/projects/NAME.json`. Do not print environment files or
credentials to discover runtime status.

In Coder, `localtest-remote status NAME` reports whether that profile's Ubuntu
bridge is online and which named actions it advertises. The profile name must
match the name configured by the user. An unknown/offline profile needs Ubuntu
setup; a folder in Coder is not itself a registration.

## Work and verify

1. Edit the registered Coder source. Saved additions, edits, and deletions sync
   without committing or pushing. Explain when work is outside that source.
2. Determine the app's reload behavior. Next/Vite usually hot reload. Custom
   apps may need `--restart-on-change` or their own watcher. Nested dependency
   locks are not automatically installed by the generic Node installer.
3. Check bridge status, then inspect startup output with the built-in actions:
   `localtest-remote run NAME status` and `localtest-remote run NAME journal 80`.
4. Run the registered health/test actions. Custom actions flush source sync
   before execution; that flush does not wait for the app to finish rebuilding.
5. Inspect exit codes and actual endpoint/test output. State where checks ran.
   Coder's localhost is not Ubuntu's localhost. Do not call a Coder browser or
   Coder HTTP endpoint proof of an Ubuntu preview.

Example Coder commands (only use actions actually advertised by this profile):

```bash
localtest-remote status myapp
localtest-remote run myapp journal 80
localtest-remote run myapp health
localtest-remote run --timeout 900 myapp test
```

## Runtime and secrets

The Ubuntu CLI is `localtest`; Coder's CLI is `localtest-remote`. The bridge
connects outbound through the user's authenticated Coder SSH transport.
It can remain online while the app is stopped or broken.

Cloud `.env` files (except examples), Git metadata, dependencies, and build
output are excluded from sync. Local overrides live in
`~/.config/localtest/env/NAME/project.env`; additional app-specific env files
belong outside the mirror too. Cloud env edits do not configure Ubuntu.
Use `localtest start NAME` on Ubuntu after changing runtime/env settings.

Simple `KEY=value` lines in `project.env` are parsed as data. There is no shell
expansion. The generic profile exports frontend `PORT`; multi-service wrappers
must set each service's port independently. For Docker guidance, including
confined installations, read `docs/PROJECTS.md`.

## Actions and interrupted requests

Only `status`, `journal`, and actions registered with `localtest action` on Ubuntu
are available. Register a project's health/tests with specific commands and a
working directory inside its mirror. Arguments are positional values, not shell
source; preserve `"$@"`. App code and registered commands execute with the Ubuntu
user's permissions, so this is not an untrusted-code execution sandbox.

Actions run serially per project, with timeouts and bounded output. A lost
connection during a data-changing action gives an **unknown outcome**. Inspect
the application's state and recorded result; do not replay it automatically.

Normal `run` rejects offline execution. `queue --expires-in 3600 NAME ACTION`
explicitly queues a request for the next connection; use it only when requested,
especially for mutations. `result JOB_ID` retrieves a recorded outcome and
`cancel JOB_ID` cancels a still-pending request. Completed results expire after
seven days. Local credentials are not transferred as files, but action output
and arguments are recorded in Coder: never put secrets there.

## When human action is needed

If you cannot access Ubuntu, provide the exact Ubuntu commands needed to install,
authenticate, register, or enable its bridge. Continue independent Coder work.
Do not claim the Ubuntu setup is complete until an online worker returns the
required checks. Adding agent instructions does not install a bridge.
