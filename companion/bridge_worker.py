"""Ubuntu-side named-action runner; connects outbound through Coder SSH."""
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import socket
import subprocess
import sys
import time

from remote import MAX_OUTPUT, Peer

COMMON = ("status", "journal")


def capabilities(p):
    return sorted(set(COMMON + tuple(p.get("actions", {}))))


def specification(p, action, params, app):
    if action not in capabilities(p):
        raise ValueError("Action is not enabled: " + action)
    root = Path(p["local_path"]).resolve()
    env = app.project_env(p)
    cwd = root if root.exists() else Path.home()
    if action == "status":
        if params:
            raise ValueError("status takes no arguments")
        return ["systemctl", "--user", "show", app.unit(p["name"]), "--property=ActiveState,SubState,Result"], cwd, env
    if action == "journal":
        if len(params) > 1:
            raise ValueError("journal accepts an optional line count")
        lines = line_count(params[0] if params else "100")
        return ["journalctl", "--user", "-u", app.unit(p["name"]), "-n", str(lines), "--all", "--output=cat", "--no-pager"], cwd, env
    config = p["actions"][action]
    cwd = (root / config.get("cwd", ".")).resolve()
    if not cwd.is_relative_to(root):
        raise ValueError("Action working directory must stay inside the project")
    # The command is registered locally by the user. Request arguments are
    # positional parameters, never interpolated into shell source.
    return ["bash", "-c", config["command"], "localtest-action", *params], cwd, env


def line_count(value):
    count = int(value)
    if not 1 <= count <= 2000:
        raise ValueError("Line count must be between 1 and 2000")
    return count


def execute(argv, cwd, env, timeout, beat):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    output, total = b"", 0
    started = last_beat = time.monotonic()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    timed_out = False
    try:
        while True:
            now = time.monotonic()
            if now - last_beat >= 5:
                beat()
                last_beat = now
            if now - started > timeout:
                timed_out = True
                break
            events = selector.select(.25)
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 16384)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                output = (output + chunk)[-MAX_OUTPUT:]
            if process.poll() is not None and not selector.get_map():
                break
    finally:
        # Also terminate descendants when a runner leaves background children.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        selector.close()
        process.stdout.close()
    return {"exit_code": 124 if timed_out else process.returncode,
            "output": output.decode(errors="replace") + ("\n[Action timed out]\n" if timed_out else ""),
            "truncated": total > MAX_OUTPUT}


def perform(job, p, app, beat):
    action, params = job["action"], job["args"]
    if not isinstance(params, list) or not all(isinstance(x, str) for x in params):
        raise ValueError("Action arguments must be strings")
    if action not in capabilities(p):
        raise ValueError("Action is not enabled: " + action)
    timeout = min(max(int(job["timeout"]), 1), 1800)
    deadline = time.monotonic() + timeout
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Action timed out")
        return value
    if action not in COMMON:
        # Run against the current saved code, not a stale local copy.
        synced = execute(["mutagen", "sync", "flush", app.sync_name(p)], Path.home(), app.project_env(p), min(remaining(), 60), beat)
        if synced["exit_code"]:
            return synced
    argv, cwd, env = specification(p, action, params, app)
    return execute(argv, cwd, env, remaining(), beat)


def run(p, app):
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    while True:
        connection = None
        try:
            p = app.load(p["name"])
            bridge = p.get("bridge", {})
            if not bridge.get("enabled"):
                return
            argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=60",
                    "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                    p["host"], shlex.join(["python3", bridge["broker"], "serve", p["name"]])]
            connection = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          env=app.project_env(p))
            peer = Peer(connection.stdout, connection.stdin)
            peer.send({"type": "hello", "project": p["name"], "host": socket.gethostname(),
                       "local_path": p["local_path"], "actions": capabilities(p)})
            print("Ubuntu command bridge connected for " + p["name"], flush=True)
            while True:
                message = peer.receive(90)
                if message.get("type") == "ping":
                    peer.send({"type": "pong"})
                    continue
                if message.get("type") != "job":
                    raise ValueError("Unexpected cloud broker message")
                job_id = message["id"]
                def beat():
                    peer.send({"type": "heartbeat", "id": job_id})
                try:
                    print("Running action: " + message["action"], flush=True)
                    result = perform(message, app.load(p["name"]), app, beat)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    result = {"exit_code": 1, "output": str(error) + "\n"}
                peer.send({"type": "result", "id": job_id, **result})
                ack = peer.receive(30)
                if ack.get("type") != "ack" or ack.get("id") != job_id:
                    raise ValueError("Missing result acknowledgement")
        except KeyboardInterrupt:
            return
        except (OSError, ValueError, EOFError, TimeoutError) as error:
            print("Bridge reconnecting: " + str(error), file=sys.stderr, flush=True)
        finally:
            if connection:
                if connection.poll() is None:
                    connection.terminate()
                    try:
                        connection.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        connection.kill()
                        connection.wait()
                connection.stdin.close()
                connection.stdout.close()
        time.sleep(5)
