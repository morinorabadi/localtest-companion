# Contributing

Keep the companion project-neutral and its runtime dependencies in Python's
standard library. Support Python 3.10+ on Linux with systemd. Do not commit local
profiles, `.env` files, queue databases, SSH config, fixtures, or generated state.

Run from the repository root:

```bash
python3 -m unittest discover -s companion -v
python3 -m compileall -q companion scripts examples
bash -n companion/install.sh companion/update.sh scripts/install-broker.sh
```

The suite tests profiles, environment parsing, command arguments, timeout/output
bounds, queue behavior, update preservation, and a real Python broker/worker
round trip using an SSH transport stub. It uses temporary directories and does
not start your existing application or systemd services.

The real Mutagen test is opt-in. Install to a temporary prefix, then enable it:

```bash
test_prefix="$(mktemp -d)"
bash companion/install.sh --prefix "$test_prefix"
LOCALTEST_TEST_MUTAGEN="$test_prefix/share/localtest/bin/mutagen" \
  python3 -m unittest discover -s companion -v
```

It runs a separate temporary Mutagen daemon and verifies real one-way file edits,
deletions, and ignored local secrets/dependencies. It does not prove Coder SSH or
an Ubuntu app works. A complete user smoke test is documented in
`examples/python-http/README.md` and requires both machines.

Review both-machine instructions when changing the CLI or installation paths.
Updates must preserve profiles, local environments, data, and unrelated services.

## Optional GitHub Actions

`docs/ci-workflow.example.yml` contains unit checks on Python 3.10/3.12 and a
real Mutagen integration job. To enable it, copy it to `.github/workflows/test.yml`
and push with credentials allowed to create GitHub Actions workflows. The initial
publication credentials do not have that permission; the template is provided
without enabling an automated workflow.
