# Agent instructions

Read `README.md` and `companion/AGENT_GUIDE.md` before setup or runtime changes.
For a new user, follow `docs/AGENT_SETUP.md`; for implementation changes, read
`CONTRIBUTING.md`. Python 3.10+ and the standard library are sufficient for tests.

## Complete the user's setup

- Determine whether you are running in Coder, native Ubuntu, Windows PowerShell,
  or Ubuntu in WSL 2. For Windows, read `docs/WINDOWS.md` and set up the local
  runtime inside WSL with working systemd user services. Keep Linux tools and
  mirrors in the Linux filesystem. Verify Windows browser access separately;
  never claim a WSL test ran unless you have actual WSL output.
- Inspect the actual
  workspace, app path, SSH alias, runtimes, and existing localtest profiles.
  Never treat the example `dev` workspace or `myapp` path as confirmed values.
- Continue work that is possible on your current machine. If authentication or
  access to the other machine requires a human, finish the local work first and
  provide exact commands labeled with their destination machine.
- Register a new or empty Ubuntu mirror. Do not reuse the development checkout
  as a one-way replica target. Keep environment files and data outside it.
- Inspect the app's existing startup documentation and select the required
  runtime before creating a profile. Capture its PATH through `localtest add`.
- Register narrowly named health/log/test actions on Ubuntu; preserve quoted
  `"$@"` when accepting positional action arguments. No dynamic shell evaluation
  of cloud arguments. Setup/start/custom commands and synced app code are trusted
  local execution, not a sandbox.
- Check `localtest-remote status NAME` before sending Ubuntu actions. Offline
  means the Ubuntu bridge must be enabled/fixed; do not substitute a Coder app.
- Verify sync, local HTTP readiness, and an actual bridge action result. Report
  what ran on each machine. Do not claim complete setup without that evidence.
- Add a reference to `companion/AGENT_GUIDE.md` (the actual absolute checkout path
  or this repo URL) in the user's app agent instructions so later sessions use
  the same workflow. Keep the guide free of secrets.

## Change the implementation

- Keep this repository project-neutral. App adapters belong in those apps;
  never add private deployment URLs, account paths, fixture exports, or keys.
- Preserve user profiles, environment values, database volumes, existing sync
  sessions, and unrelated services. Do not stop all Mutagen/systemd services.
- Keep the bridge independent of the app. Never automatically replay a job with
  an unknown outcome after a lost connection.
- Run `python3 -m unittest discover -s companion -v`. For synchronization changes,
  also run the real Mutagen integration test as described in `CONTRIBUTING.md`.
- Installation/update behavior and both-machine setup docs are part of the
  product; update them together when paths or CLI semantics change.
