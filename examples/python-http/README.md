# End-to-end smoke example

This Python standard-library server proves the infrastructure before you add
your real app. First install both sides using the root README. Substitute your
actual workspace and Coder tool checkout path; the commands below use `dev` and
`/home/coder/localtest-companion` as examples. Port 7088 must be unused on Ubuntu.

Run **on Ubuntu**:

```bash
localtest add localtest-smoke --workspace dev \
  --remote /home/coder/localtest-companion/examples/python-http --port 7088 \
  --start 'python3 -u -m http.server "$PORT" --bind 127.0.0.1'
localtest action localtest-smoke health --command 'python3 health.py'
localtest start localtest-smoke
localtest bridge enable localtest-smoke \
  --broker /home/coder/localtest-companion/companion/remote.py
localtest run localtest-smoke health
```

Run **inside Coder** after the bridge connects:

```bash
localtest-remote status localtest-smoke
localtest-remote run localtest-smoke health
printf 'saved in Coder and served on Ubuntu\n' > /home/coder/localtest-companion/examples/python-http/hello.txt
localtest-remote run localtest-smoke health
```

The second action must print `HTTP 200: saved in Coder and served on Ubuntu`.
That returned body is evidence that a saved source change reached Ubuntu and the
local server served it back through an action. Open
http://localhost:7088/hello.txt on Ubuntu if desired.

Restore the tracked example in Coder when done:

```bash
git -C /home/coder/localtest-companion restore examples/python-http/hello.txt
```

Stop just this example **on Ubuntu**:

```bash
localtest stop localtest-smoke
localtest bridge disable localtest-smoke
```

These checks prove the example transport. They do not prove your separate
application's dependencies, provider credentials, migrations, or workflow tests.
