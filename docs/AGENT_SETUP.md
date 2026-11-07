# Give this prompt to your coding agent

This works with agents that can read files and run terminal commands. It does not
require a particular model, editor, or app connector. The agent can work in Coder
or on Ubuntu, but one machine cannot be assumed to have shell access to the other.

Copy this prompt and fill in any details you know:

```text
Set up the Ubuntu localtest companion for my project:
https://github.com/morinorabadi/localtest-companion

Clone or inspect the repository, then read AGENTS.md, README.md,
companion/AGENT_GUIDE.md, and docs/PROJECTS.md. Carry out the setup steps available
on this machine; don't stop at writing a plan.

My Coder deployment: [URL, or discover/ask]
My Coder workspace: [workspace name, or discover/ask]
My app's absolute path inside Coder: [path, or discover/ask]
My preferred local profile name and port: [name/port, or choose unused values]
My app's startup/test commands: [commands, or inspect the app's documentation]

First identify whether you are in Coder or on Ubuntu. Inspect existing profiles
and runtimes. Keep the tool checkout separate from the app source and use a new
or empty Ubuntu mirror. Keep secrets and local data outside synced sources.

Install the Coder broker and Ubuntu companion, configure the actual SSH alias,
register the app with the right startup commands, and enable its independent
bridge. Register useful health and test actions for this app.

If you cannot reach the other machine, finish what you can here and give me a
short, exact command block labeled with the machine where I must run it. Let me
complete interactive authentication; never ask me to paste tokens into chat.

Verify a source edit reaches Ubuntu, the app's HTTP health endpoint succeeds
there, and the Coder broker receives an actual Ubuntu action result. Use the
included Python smoke example first if the infrastructure needs diagnosis.
An active systemd service or successful source sync alone is not sufficient.

Add a pointer to the agent runtime guide in my app's agent instructions. Finish
with the local URL, profile/config paths, successful checks and their machine,
and any remaining blocker. Preserve unrelated profiles and services.
```

## Completion evidence

The agent should establish all of the following before reporting full setup:

- Coder has the tool checkout, Python broker, and `localtest-remote` command.
- Ubuntu has the companion, required app runtimes, and a working Coder SSH alias.
- The profile records the actual Coder source, unused port, and empty/new mirror.
- A saved file change propagates from Coder to the Ubuntu mirror.
- The app starts and an HTTP readiness probe succeeds on Ubuntu.
- `localtest-remote status NAME` is online and lists the intended actions.
- A named health/test action completes and returns its actual result to Coder.
- Future agents can find `companion/AGENT_GUIDE.md` from the app's instructions.

The included smoke example proves the transport with a small local server.
Your real application's readiness and test results are separate checks.
