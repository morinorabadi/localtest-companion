#!/usr/bin/env python3
"""Cloud request queue and SSH stdio broker for the Ubuntu localtest worker."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import sqlite3
import sys
import time
import uuid

STORE = Path(os.environ.get("LOCALTEST_REMOTE_STATE", "~/.local/state/localtest-remote")).expanduser()
MAX_OUTPUT = 128 * 1024


def valid_name(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", value):
        raise ValueError("Invalid project/action name")
    return value


class Peer:
    def __init__(self, reader, writer):
        self.reader, self.writer, self.buffer = reader, writer, b""

    def send(self, value):
        self.writer.write(json.dumps(value).encode() + b"\n")
        self.writer.flush()

    def receive(self, timeout=30):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.reader], [], [], remaining)[0]:
                raise TimeoutError("Bridge peer stopped responding")
            data = os.read(self.reader.fileno(), 65536)
            if not data:
                raise EOFError("Bridge connection closed")
            self.buffer += data
            if len(self.buffer) > 2 * 1024 * 1024:
                raise ValueError("Bridge frame too large")
        line, self.buffer = self.buffer.split(b"\n", 1)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("Invalid bridge frame")
        return value


def database():
    STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(STORE / "queue.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS workers (
      project TEXT PRIMARY KEY, heartbeat REAL, online INTEGER, details TEXT);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, project TEXT, action TEXT, args TEXT, timeout INTEGER,
      created REAL, expires REAL, status TEXT, result TEXT);
    """)
    with db:
        db.execute("DELETE FROM jobs WHERE created < ? AND status IN ('done','cancelled')", (time.time() - 7 * 86400,))
    (STORE / "queue.sqlite3").chmod(0o600)
    return db


def worker_status(db, project):
    row = db.execute("SELECT * FROM workers WHERE project=?", (project,)).fetchone()
    if row is None:
        return {"project": project, "online": False, "reason": "Ubuntu bridge has not connected"}
    return {"project": project, "online": bool(row["online"] and time.time() - row["heartbeat"] < 30),
            "last_seen_seconds_ago": round(time.time() - row["heartbeat"], 1),
            **json.loads(row["details"])}


def submit(db, project, action, args, timeout, allow_offline=False, ttl=None):
    status = worker_status(db, project)
    if not status["online"] and not allow_offline:
        raise ValueError("Ubuntu bridge is offline. Enable it on Ubuntu with: localtest bridge enable " + project)
    if status["online"] and action not in status.get("actions", []):
        raise ValueError("Action is not enabled on Ubuntu: " + action)
    job_id = uuid.uuid4().hex
    now = time.time()
    with db:
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,NULL)",
                   (job_id, project, action, json.dumps(args), timeout, now, now + (ttl if ttl is not None else timeout + 30), "pending"))
    return job_id


def complete(db, job_id, result):
    output = str(result.get("output", ""))
    result = {"exit_code": int(result.get("exit_code", 1)), "output": output[-MAX_OUTPUT:],
              "truncated": bool(result.get("truncated", False) or len(output) > MAX_OUTPUT),
              "finished_at": time.time()}
    with db:
        db.execute("UPDATE jobs SET status='done', result=? WHERE id=?", (json.dumps(result), job_id))


def serve(project):
    valid_name(project)
    db = database()
    lock = (STORE / (project + ".lock")).open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    peer = Peer(sys.stdin.buffer, sys.stdout.buffer)
    hello = peer.receive(15)
    if hello.get("type") != "hello" or hello.get("project") != project:
        raise ValueError("Unexpected worker handshake")
    details = {k: hello.get(k) for k in ("host", "local_path", "actions")}
    if not isinstance(details["actions"], list):
        raise ValueError("Worker did not advertise its actions")
    def heartbeat():
        with db:
            db.execute("INSERT OR REPLACE INTO workers VALUES (?,?,1,?)", (project, time.time(), json.dumps(details)))
    # An interrupted job may have already changed data. Never replay it.
    for job in db.execute("SELECT id FROM jobs WHERE project=? AND status='running'", (project,)).fetchall():
        complete(db, job["id"], {"exit_code": 255, "output": "Worker connection was interrupted; outcome is unknown. Job was not replayed."})
    heartbeat()
    active = None
    try:
        while True:
            heartbeat()
            job = db.execute("SELECT * FROM jobs WHERE project=? AND status='pending' ORDER BY created LIMIT 1", (project,)).fetchone()
            if job:
                if job["expires"] < time.time():
                    complete(db, job["id"], {"exit_code": 124, "output": "Request expired before execution"})
                    continue
                active = job["id"]
                with db:
                    claimed = db.execute("UPDATE jobs SET status='running' WHERE id=? AND status='pending'", (active,)).rowcount
                if not claimed:
                    active = None
                    continue
                peer.send({"type": "job", "id": active, "action": job["action"],
                           "args": json.loads(job["args"]), "timeout": job["timeout"]})
                while True:
                    response = peer.receive(30)
                    heartbeat()
                    if response.get("id") != active:
                        raise ValueError("Worker responded for the wrong job")
                    if response.get("type") == "heartbeat":
                        continue
                    if response.get("type") != "result":
                        raise ValueError("Unexpected job response")
                    complete(db, active, response)
                    peer.send({"type": "ack", "id": active})
                    active = None
                    break
            else:
                peer.send({"type": "ping"})
                if peer.receive(15).get("type") != "pong":
                    raise ValueError("Unexpected keepalive response")
                time.sleep(1)
    finally:
        if active:
            complete(db, active, {"exit_code": 255, "output": "Connection interrupted during execution; outcome is unknown. Job was not replayed."})
        with db:
            db.execute("UPDATE workers SET online=0 WHERE project=?", (project,))
        lock.close()
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "serve"):
        sub.add_parser(command).add_argument("project", type=valid_name)
    for command in ("run", "queue"):
        r = sub.add_parser(command)
        r.add_argument("--timeout", type=int, default=600)
        if command == "queue":
            r.add_argument("--expires-in", type=int, default=3600)
        r.add_argument("project", type=valid_name)
        r.add_argument("action", type=valid_name)
        r.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("result").add_argument("job_id")
    sub.add_parser("cancel").add_argument("job_id")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.project)
        return 0
    db = database()
    if args.command == "status":
        status = worker_status(db, args.project)
        print(json.dumps(status, indent=2))
        return 0 if status["online"] else 1
    if args.command in ("run", "queue"):
        if not 1 <= args.timeout <= 1800:
            raise ValueError("Timeout must be between 1 and 1800 seconds")
        params = args.args[1:] if args.args[:1] == ["--"] else args.args
        if len(json.dumps(params)) > 128 * 1024:
            raise ValueError("Request arguments are too large")
        ttl = args.expires_in if args.command == "queue" else None
        if ttl is not None and not 1 <= ttl <= 86400:
            raise ValueError("Queue expiry must be between 1 and 86400 seconds")
        job_id = submit(db, args.project, args.action, params, args.timeout,
                        allow_offline=args.command == "queue", ttl=ttl)
        if args.command == "queue":
            print(json.dumps({"job_id": job_id, "status": "pending", "expires_in_seconds": ttl}))
            return 0
        print(f"Ubuntu job {job_id}: {args.project}/{args.action}", file=sys.stderr, flush=True)
        deadline = time.monotonic() + args.timeout + 35
        try:
            while time.monotonic() < deadline:
                row = db.execute("SELECT result FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row["result"]:
                    result = json.loads(row["result"])
                    print(result["output"], end="" if result["output"].endswith("\n") else "\n")
                    if result["truncated"]:
                        print("[Output limited to its last 128 KiB]", file=sys.stderr)
                    return result["exit_code"] if 0 <= result["exit_code"] <= 255 else 1
                time.sleep(.25)
        finally:
            # Cancel only requests not yet started. Running jobs are not replayed.
            with db:
                db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'", (job_id,))
        print("Timed out waiting. Retrieve the result with: localtest-remote result " + job_id, file=sys.stderr)
        return 124
    if args.command == "cancel":
        with db:
            changed = db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'", (args.job_id,)).rowcount
        if not changed:
            raise ValueError("Job was not pending; it cannot be cancelled or replayed by this command")
        print("Cancelled pending job " + args.job_id)
        return 0
    row = db.execute("SELECT * FROM jobs WHERE id=?", (args.job_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown job ID")
    print(json.dumps(dict(row), indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, EOFError, TimeoutError) as error:
        print("localtest-remote: " + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
