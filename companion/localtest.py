#!/usr/bin/env python3
"""Ubuntu companion: named project profiles, Mutagen sync, systemd supervision."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

CONFIG = Path(os.environ.get("LOCALTEST_CONFIG_DIR", "~/.config/localtest")).expanduser()
STATE = Path(os.environ.get("LOCALTEST_STATE_DIR", "~/.local/state/localtest")).expanduser()
BASE_IGNORES = [
    ".git", "node_modules", ".next", "dist", "build", "out", "coverage", ".turbo",
    ".venv", "venv", "__pycache__", ".pytest_cache", "*.pyc", "*.tsbuildinfo",
    ".env", ".env.*", "!.env.example", "!.env.*.example", "*.log",
    ".localtest", ".state", "**/src/generated/prisma",
    ".codex-worktrees", ".worktrees", ".recovery",
]
STOP = threading.Event()
os.environ["MUTAGEN_DATA_DIRECTORY"] = str(STATE / "sync")


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def name_ok(name):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", name):
        raise ValueError("Project names must be lowercase letters, digits or hyphens; start with a letter.")
    return name


def profile_path(name):
    return CONFIG / "projects" / (name_ok(name) + ".json")


def load(name):
    return json.loads(profile_path(name).read_text())


def unit(name):
    return f"localtest-{name_ok(name)}.service"


def sync_name(p):
    return "localtest-" + p["name"]


def require(*commands):
    missing = [c for c in commands if not shutil.which(c)]
    if missing:
        raise ValueError("Install missing commands: " + ", ".join(missing))


def project_env(p):
    env = dict(os.environ)
    env["PATH"] = p["path"]
    env["COMPOSE_PROJECT_NAME"] = "localtest-" + p["name"]
    env["PORT"] = str(p["port"])
    env.update(env_values(Path(p["env_file"])))
    return env


def env_values(file):
    env = {}
    for number, line in enumerate(file.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid environment entry at {file}:{number}")
        value = value.strip()
        if value.startswith(('"', "'")):
            parts = shlex.split(value, comments=True)
            if len(parts) != 1:
                raise ValueError(f"Invalid quoted value at {file}:{number}")
            value = parts[0]
        env[key] = value
    return env


def save_profile(p):
    target = profile_path(p["name"])
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(p, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)


def shell(command, p):
    # Commands come from the user's local profile; env values are never evaluated.
    return run(["bash", "-c", command], cwd=p["local_path"], env=project_env(p))


def add(args):
    name = name_ok(args.name)
    target = profile_path(name)
    if target.exists():
        raise ValueError(f"{name} already exists. Edit {target}, then run localtest start {name}.")
    if not args.remote.startswith("/") or any(c in args.remote for c in "\n\r"):
        raise ValueError("--remote must be an absolute workspace folder path.")
    host = args.host or args.workspace + ".coder"
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", host) or host.startswith("-"):
        raise ValueError("Invalid SSH host. Use --host with the alias from coder config-ssh.")
    local = Path(args.local or f"~/localtest/{name}").expanduser().resolve()
    if local.exists() and any(local.iterdir()):
        raise ValueError("Choose a new or empty --local folder; Coder will be its source of truth.")
    profiles = [load(f.stem) for f in (CONFIG / "projects").glob("*.json")]
    for p in profiles:
        other = Path(p["local_path"])
        if local == other or local in other.parents or other in local.parents:
            raise ValueError(f"Local folder overlaps project {p['name']}.")
    used = {p["port"] for p in profiles}
    port = args.port or next(i for i in range(3000, 65000) if i not in used)
    if not 1024 <= port <= 65535:
        raise ValueError("--port must be between 1024 and 65535.")
    if port in used:
        raise ValueError("Port is reserved by another profile.")
    env_dir = CONFIG / "env" / name
    env_dir.mkdir(parents=True, mode=0o700)
    for filename in ("project.env",):
        f = env_dir / filename
        if not f.exists():
            f.write_text("# Local environment overrides. KEY=value; no shell expansion.\n")
            f.chmod(0o600)
    p = dict(name=name, workspace=args.workspace, host=host, remote_path=args.remote,
             local_path=str(local), port=port,
             env_file=str(env_dir / "project.env"), path=os.environ["PATH"],
             setup=args.setup, start=args.start, stop=args.stop,
             restart_on_change=args.restart_on_change,
             url=args.url or f"http://localhost:{port}", ignores=args.ignore)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_text(json.dumps(p, indent=2) + "\n")
    target.chmod(0o600)
    print(f"Added {name}. Config: {target}\nLocal env: {env_dir}\nStart: localtest start {name}")


def ensure_sync(p):
    require("mutagen", "ssh")
    local = Path(p["local_path"])
    local.mkdir(parents=True, exist_ok=True)
    # The dedicated daemon runs in its own systemd cgroup, so stopping one
    # project cannot kill sync for the other projects.
    run(["systemctl", "--user", "start", "localtest-sync.service"])
    listing = run(["mutagen", "sync", "list", "--template={{range .}}{{.Name}}{{\"\\n\"}}{{end}}"],
                  capture_output=True, text=True).stdout.splitlines()
    name = sync_name(p)
    # The signature prevents silently reusing a session after endpoints/ignores change.
    signature = hashlib.sha256(json.dumps([p["host"], p["remote_path"], str(local), BASE_IGNORES, p["ignores"]]).encode()).hexdigest()
    marker = STATE / p["name"] / "sync-signature"
    if name in listing and (not marker.exists() or marker.read_text() != signature):
        run(["mutagen", "sync", "terminate", name])
        listing.remove(name)
    if name not in listing:
        args = ["mutagen", "sync", "create", "--no-global-configuration", "--name", name,
                "--sync-mode", "one-way-replica", "--ignore-vcs"]
        for pattern in BASE_IGNORES + p["ignores"]:
            args += ["--ignore", pattern]
        args += [p["host"] + ":" + p["remote_path"], str(local)]
        run(args, timeout=120)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(signature)
    else:
        run(["mutagen", "sync", "resume", name], timeout=30)
    ready = marker.parent / "initial-sync"
    cached = ready.exists() and ready.read_text() == signature
    print("Waiting for sync; first download may take several minutes.", flush=True)
    try:
        run(["mutagen", "sync", "flush", name], timeout=20 if cached else 900)
        ready.write_text(signature)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if not cached:
            raise
        print("Workspace unavailable. Running cached code; Mutagen will reconnect automatically.", flush=True)


def digest(paths):
    result = hashlib.sha256()
    for path in paths:
        if path.is_file():
            result.update(str(path).encode())
            result.update(path.read_bytes())
    return result.hexdigest()


def source_stamp(root):
    """Cheap local change detection, ignoring local/generated runtime content."""
    h = hashlib.sha256()
    excluded = {"node_modules", ".git", ".next", "dist", "build", "out", ".state",
                "coverage", ".turbo", ".venv", "venv", "__pycache__", "generated"}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".mutagen"))
        for name in sorted(files):
            if name.endswith((".log", ".tsbuildinfo")) or name == ".env" or name.startswith(".env."):
                continue
            f = Path(base) / name
            try:
                s = f.stat()
                h.update(f"{f}:{s.st_size}:{s.st_mtime_ns}".encode())
            except FileNotFoundError:
                pass  # A new sync cycle can delete a file while we scan.
    return h.hexdigest()


def install_node(p, folder):
    locks = [folder / n for n in ("package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock")]
    key = digest(locks)
    stamp = STATE / p["name"] / (hashlib.sha256(str(folder).encode()).hexdigest()[:12] + ".deps")
    if stamp.exists() and stamp.read_text() == key and (folder / "node_modules").exists():
        return
    if (folder / "pnpm-lock.yaml").exists():
        cmd = ["pnpm", "install", "--frozen-lockfile"]
    elif (folder / "package-lock.json").exists():
        cmd = ["npm", "ci"]
    else:
        raise ValueError(f"No supported lockfile in {folder}. Set --setup to your install command.")
    run(cmd, cwd=folder, env=project_env(p))
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(key)


def node_command(p):
    root = Path(p["local_path"])
    pkg = json.loads((root / "package.json").read_text())
    manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "next" in deps:
        prefix = "pnpm exec" if manager == "pnpm" else "npm exec --"
        return f"{prefix} next dev --hostname 127.0.0.1 --port {p['port']}"
    if "vite" in deps:
        prefix = "pnpm exec" if manager == "pnpm" else "npm exec --"
        return f"{prefix} vite --host 127.0.0.1 --port {p['port']} --strictPort"
    if "dev" not in pkg.get("scripts", {}):
        raise ValueError("No dev script detected. Edit the profile's start command.")
    return f"{manager} run dev"


def service_run(p):
    os.environ["PATH"] = p["path"]
    child = None
    runtime_attempted = False
    def stopped(signum, frame):
        STOP.set()
        if child and child.poll() is None:
            child.terminate()
        # A setup/sync subprocess may be running. systemd also signals the cgroup.
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    try:
        ensure_sync(p)
        root = Path(p["local_path"])
        def setup():
            if p["setup"]:
                shell(p["setup"], p)
            elif not p["start"]:
                install_node(p, root)
        setup()
        command = p["start"] or node_command(p)
        def start_child():
            print(f"Starting {p['name']}: {p['url']}", flush=True)
            return subprocess.Popen(["bash", "-c", command], cwd=root, env=project_env(p), start_new_session=True)
        runtime_attempted = True
        child = start_child()
        last = source_stamp(root) if p["restart_on_change"] else None
        locks = lambda: digest([root / n for n in ("package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock")] + [Path(p["env_file"])])
        deps = locks()
        while not STOP.wait(2):
            if child.poll() is not None:
                raise ValueError(f"App command exited ({child.returncode}); systemd will retry.")
            current = source_stamp(root) if p["restart_on_change"] else None
            changed_deps = locks() != deps
            if changed_deps or current != last:
                if STOP.wait(2) or (current is not None and current != source_stamp(root)):
                    continue
                stop_child(child)
                if changed_deps:
                    setup()
                    deps = locks()
                child = start_child()
                last = current
    except KeyboardInterrupt:
        pass
    finally:
        original_error = sys.exc_info()[1]
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if child:
                stop_child(child)
            if runtime_attempted and p["stop"] and Path(p["local_path"]).exists():
                shell(p["stop"], p)
        except (OSError, ValueError, subprocess.SubprocessError) as cleanup_error:
            print(f"localtest: cleanup failed: {cleanup_error}", file=sys.stderr)
            if original_error is None:
                raise


def stop_child(child):
    try:
        os.killpg(child.pid, signal.SIGTERM)
        child.wait(timeout=15)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()


def systemd_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def bridge_control(p, action, broker=None):
    name = "localtest-bridge-" + p["name"] + ".service"
    if action == "status":
        subprocess.run(["systemctl", "--user", "status", name, "--no-pager"])
        return
    if action == "disable":
        p.setdefault("bridge", {})["enabled"] = False
        save_profile(p)
        run(["systemctl", "--user", "disable", "--now", name])
        return
    require("ssh", "systemctl")
    broker = broker or p.get("bridge", {}).get("broker")
    if not broker:
        raise ValueError("Pass --broker with the absolute path of companion/remote.py inside Coder")
    if not broker.startswith("/") or any(c in broker for c in "\r\n"):
        raise ValueError("Broker path must be an absolute path inside Coder")
    p["bridge"] = {"enabled": True, "broker": broker}
    save_profile(p)
    units = Path.home() / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    (units / name).write_text(f"""[Unit]
Description=Ubuntu command bridge for {p['name']}
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={systemd_quote(sys.executable)} {systemd_quote(Path(__file__).resolve())} _bridge {p['name']}
Environment=PYTHONUNBUFFERED=1
Environment={systemd_quote('LOCALTEST_CONFIG_DIR=' + str(CONFIG.resolve()))}
Environment={systemd_quote('LOCALTEST_STATE_DIR=' + str(STATE.resolve()))}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillMode=control-group

[Install]
WantedBy=default.target
""")
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", name])
    run(["systemctl", "--user", "restart", name])
    print("Enabled Ubuntu command bridge for " + p["name"])
    print("Cloud check: localtest-remote status " + p["name"])


def start(p):
    require("systemctl", "mutagen", "ssh")
    run(["systemctl", "--user", "show-environment"], stdout=subprocess.DEVNULL)
    units = Path.home() / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    executable = Path(__file__).resolve()
    sync_service = f"""[Unit]
Description=File synchronization for localtest projects
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={systemd_quote(shutil.which('mutagen'))} daemon run
Environment={systemd_quote('MUTAGEN_DATA_DIRECTORY=' + str(STATE / 'sync'))}
Environment=MUTAGEN_SSH_CONNECT_TIMEOUT=60
Restart=on-failure
RestartSec=3
"""
    (units / "localtest-sync.service").write_text(sync_service)
    content = f"""[Unit]
Description=Local testing companion for {p['name']}
StartLimitIntervalSec=0
Wants=localtest-sync.service
After=localtest-sync.service

[Service]
Type=simple
ExecStart={systemd_quote(sys.executable)} {systemd_quote(executable)} _run {p['name']}
Environment=PYTHONUNBUFFERED=1
Environment={systemd_quote('LOCALTEST_CONFIG_DIR=' + str(CONFIG.resolve()))}
Environment={systemd_quote('LOCALTEST_STATE_DIR=' + str(STATE.resolve()))}
Restart=on-failure
RestartSec=15
TimeoutStopSec=60
KillMode=control-group

[Install]
WantedBy=default.target
"""
    (units / unit(p["name"])).write_text(content)
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", unit(p["name"])])
    run(["systemctl", "--user", "restart", unit(p["name"])])
    print(f"Starting {p['name']} in the background. Follow progress: localtest logs {p['name']}")
    print("Enabled at login. For startup before login: sudo loginctl enable-linger \"$USER\"")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    a = sub.add_parser("add", help="Register any project (does not start it)")
    a.add_argument("name")
    a.add_argument("--workspace", default="dev")
    a.add_argument("--host", help="SSH alias; defaults to WORKSPACE.coder")
    a.add_argument("--remote", required=True)
    a.add_argument("--local", help="New/empty local mirror; defaults to ~/localtest/NAME")
    a.add_argument("--setup", default="", help="Install/setup command, run locally")
    a.add_argument("--start", default="", help="Foreground run command; otherwise detect Node/Next/Vite")
    a.add_argument("--stop", default="", help="Optional cleanup command, e.g. docker compose stop")
    a.add_argument("--port", type=int)
    a.add_argument("--url")
    a.add_argument("--ignore", action="append", default=[], help="Additional Mutagen ignore; repeatable")
    a.add_argument("--restart-on-change", action="store_true", help="Restart an app without native hot reload")
    for action in ("start", "stop", "logs", "sync-status", "config", "_run", "_bridge"):
        s = sub.add_parser(action)
        s.add_argument("name")
    sub.add_parser("status")
    sub.add_parser("doctor")
    bridge = sub.add_parser("bridge", help="Enable/disable the outbound command bridge")
    bridge.add_argument("bridge_action", choices=["enable", "disable", "status"])
    bridge.add_argument("name")
    bridge.add_argument("--broker", help="Absolute Coder path of companion/remote.py; required the first time")
    action = sub.add_parser("action", help="Register a custom named command on Ubuntu")
    action.add_argument("name")
    action.add_argument("action_name")
    action.add_argument("--command", required=True)
    action.add_argument("--cwd", default=".")
    local_run = sub.add_parser("run", help="Run one named bridge action directly on Ubuntu")
    local_run.add_argument("name")
    local_run.add_argument("task")
    local_run.add_argument("params", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "add":
        add(args)
    elif args.action == "doctor":
        for c in ("coder", "ssh", "mutagen", "systemctl", "git", "node", "npm", "pnpm", "docker"):
            print(f"{c}: {shutil.which(c) or 'not installed'}")
        print("Coder connection: coder list; ssh dev.coder true")
        print("Docker permissions: docker info")
    elif args.action == "status":
        for f in sorted((CONFIG / "projects").glob("*.json")):
            p = load(f.stem)
            state = subprocess.run(["systemctl", "--user", "is-active", unit(p["name"])], capture_output=True, text=True)
            print(f"{p['name']}: {state.stdout.strip() or 'unknown'} | {p['url']} | {p['local_path']}")
        print("Service active means the companion is running; app readiness appears in localtest logs NAME.")
    else:
        p = load(args.name)
        if args.action == "start":
            start(p)
        elif args.action == "stop":
            run(["systemctl", "--user", "disable", "--now", unit(p["name"])])
            run(["mutagen", "sync", "pause", sync_name(p)])
        elif args.action == "logs":
            run(["journalctl", "--user", "-u", unit(p["name"]), "-n", "80", "-f",
                 "--all", "--output=cat", "--no-pager"])
        elif args.action == "sync-status":
            run(["mutagen", "sync", "list", sync_name(p)])
        elif args.action == "config":
            print(profile_path(p["name"]))
        elif args.action == "_run":
            service_run(p)
        elif args.action == "bridge":
            bridge_control(p, args.bridge_action, args.broker)
        elif args.action == "action":
            name_ok(args.action_name)
            from bridge_worker import COMMON
            if args.action_name in COMMON:
                raise ValueError("Cannot replace a built-in action")
            root = Path(p["local_path"]).resolve()
            if not (root / args.cwd).resolve().is_relative_to(root):
                raise ValueError("Action working directory must stay inside the project")
            p.setdefault("actions", {})[args.action_name] = {"command": args.command, "cwd": args.cwd}
            save_profile(p)
            print("Registered action. Reload advertised actions: localtest bridge enable " + p["name"])
        elif args.action == "_bridge":
            import bridge_worker
            bridge_worker.run(p, sys.modules[__name__])
        elif args.action == "run":
            import bridge_worker
            result = bridge_worker.perform({"action": args.task, "args": args.params, "timeout": 600},
                                           p, sys.modules[__name__], lambda: None)
            print(result["output"], end="" if result["output"].endswith("\n") else "\n")
            if result["exit_code"]:
                sys.exit(result["exit_code"] if result["exit_code"] > 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"localtest: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
