import importlib.util
import json
import os
import shlex
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import bridge_worker as worker
import remote

spec = importlib.util.spec_from_file_location("localtest_bridge_app", Path(__file__).with_name("localtest.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class Bridge(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        env = self.root / "project.env"
        env.write_text("TEST_TOKEN=local-value\n")
        self.p = dict(name="demo", path=os.environ["PATH"], local_path=str(self.project),
                      port=3000, env_file=str(env), actions={"echo": {"command": 'printf "%s\\n" "$@"', "cwd": "."}})
        self.store = patch.object(remote, "STORE", self.root / "cloud")
        self.store.start()

    def tearDown(self):
        self.store.stop()
        self.temp.cleanup()

    def test_named_action_arguments_are_literal_and_paths_are_confined(self):
        marker = self.root / "should-not-exist"
        argument = f"$(touch {marker}); echo injected"
        argv, cwd, env = worker.specification(self.p, "echo", [argument], app)
        result = worker.execute(argv, cwd, env, 5, lambda: None)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["output"], argument + "\n")
        self.assertFalse(marker.exists())
        with self.assertRaisesRegex(ValueError, "not enabled"):
            worker.specification(self.p, "arbitrary-shell", ["anything"], app)
        self.p["actions"]["echo"]["cwd"] = "../"
        with self.assertRaisesRegex(ValueError, "inside"):
            worker.specification(self.p, "echo", [], app)

    def test_output_cap_and_timeout(self):
        result = worker.execute([sys.executable, "-c", "print('x'*200000)"], self.project, os.environ, 5, lambda: None)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["output"]), remote.MAX_OUTPUT)
        result = worker.execute([sys.executable, "-c", "import time; time.sleep(10)"], self.project, os.environ, .1, lambda: None)
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("timed out", result["output"])


    def test_offline_requests_are_not_queued(self):
        db = remote.database()
        with self.assertRaisesRegex(ValueError, "offline"):
            remote.submit(db, "demo", "echo", [], 5)
        self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
        db.close()

    def test_explicit_offline_queue_has_expiry(self):
        db = remote.database()
        job_id = remote.submit(db, "demo", "echo", [], 5, allow_offline=True, ttl=60)
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        self.assertEqual(job["status"], "pending")
        self.assertAlmostEqual(job["expires"] - job["created"], 60)
        db.close()

    def test_real_broker_roundtrip_and_interrupted_job_is_not_replayed(self):
        env = dict(os.environ, LOCALTEST_REMOTE_STATE=str(remote.STORE))
        broker = subprocess.Popen([sys.executable, str(Path(remote.__file__)), "serve", "demo"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        peer = remote.Peer(broker.stdout, broker.stdin)
        peer.send({"type": "hello", "project": "demo", "host": "test-ubuntu", "local_path": str(self.project), "actions": ["echo"]})
        db = remote.database()
        try:
            self.assertEqual(peer.receive(5)["type"], "ping")
            peer.send({"type": "pong"})
            self.assertTrue(remote.worker_status(db, "demo")["online"])
            first = remote.submit(db, "demo", "echo", ["from Ubuntu"], 5)
            job = peer.receive(5)
            self.assertEqual(job["id"], first)
            argv, cwd, local_env = worker.specification(self.p, job["action"], job["args"], app)
            result = worker.execute(argv, cwd, local_env, 5, lambda: None)
            peer.send({"type": "result", "id": first, **result})
            self.assertEqual(peer.receive(5)["type"], "ack")
            stored = json.loads(db.execute("SELECT result FROM jobs WHERE id=?", (first,)).fetchone()[0])
            self.assertEqual(stored["output"], "from Ubuntu\n")
            self.assertEqual(stored["exit_code"], 0)
            self.assertEqual(peer.receive(5)["type"], "ping")
            peer.send({"type": "pong"})
            second = remote.submit(db, "demo", "echo", ["unknown outcome"], 5)
            self.assertEqual(peer.receive(5)["id"], second)
            broker.stdin.close()
            broker.wait(timeout=5)
            row = db.execute("SELECT * FROM jobs WHERE id=?", (second,)).fetchone()
            self.assertEqual(row["status"], "done")
            self.assertIn("not replayed", json.loads(row["result"])["output"])
            self.assertFalse(remote.worker_status(db, "demo")["online"])
        finally:
            if broker.poll() is None:
                broker.terminate()
                broker.wait(timeout=5)
            for stream in (broker.stdin, broker.stdout, broker.stderr):
                if not stream.closed:
                    stream.close()
            db.close()

    def test_bridge_service_is_independent_of_app_and_preserves_profile(self):
        config, state = self.root / "config", self.root / "state"
        (config / "projects").mkdir(parents=True)
        with patch.object(app, "CONFIG", config), patch.object(app, "STATE", state), \
                patch.object(Path, "home", return_value=self.root), patch.object(app, "run"), patch.object(app, "require"):
            app.bridge_control(self.p, "enable", "/cloud/remote.py")
            profile = app.load("demo")
            self.assertEqual(profile["actions"], self.p["actions"])
            self.assertTrue(profile["bridge"]["enabled"])
        unit = (self.root / ".config/systemd/user/localtest-bridge-demo.service").read_text()
        self.assertIn("_bridge demo", unit)
        self.assertNotIn("Requires=localtest-demo", unit)

    def test_first_bridge_enable_requires_explicit_coder_broker_path(self):
        with patch.object(app, "require"), patch.object(app, "run") as run:
            with self.assertRaisesRegex(ValueError, "Pass --broker"):
                app.bridge_control(self.p, "enable")
            run.assert_not_called()

    def test_update_preserves_data_and_installs_runnable_bridge_modules(self):
        prefix = self.root / "installed"
        target = prefix / "share/localtest"
        target.mkdir(parents=True)
        (target / "localtest.py").write_text("# older version\n")
        (target / "preserve-me").write_text("existing data")
        result = subprocess.run(["bash", str(Path(app.__file__).with_name("update.sh"))],
                                env=dict(os.environ, LOCALTEST_INSTALL_PREFIX=str(prefix)),
                                capture_output=True, text=True, check=True)
        self.assertIn("preserved", result.stdout)
        self.assertEqual((target / "preserve-me").read_text(), "existing data")
        self.assertTrue((target / "bridge_worker.py").exists())
        subprocess.run([sys.executable, str(target / "localtest.py"), "--help"], check=True, capture_output=True)
        subprocess.run([sys.executable, "-c", "import bridge_worker,remote"], cwd=target, check=True)

    def test_full_worker_and_cloud_cli_with_local_ssh_transport_stub(self):
        bindir = self.root / "bin"
        bindir.mkdir()
        ssh = bindir / "ssh"
        ssh.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(Path(remote.__file__)), "serve", "demo"]) + "\n")
        ssh.chmod(0o755)
        mutagen = bindir / "mutagen"
        mutagen.write_text("#!/bin/sh\nexit 0\n")
        mutagen.chmod(0o755)
        self.p["path"] = str(bindir) + ":" + os.environ["PATH"]
        self.p["host"] = "dev.coder"
        self.p["bridge"] = {"enabled": True, "broker": "/cloud/remote.py"}
        self.p["actions"]["echo"]["command"] = 'printf "%s:%s\\n" "$TEST_TOKEN" "$1"'
        config = self.root / "config"
        (config / "projects").mkdir(parents=True)
        (config / "projects/demo.json").write_text(json.dumps(self.p))
        env = dict(os.environ, LOCALTEST_CONFIG_DIR=str(config), LOCALTEST_STATE_DIR=str(self.root / "local-state"),
                   LOCALTEST_REMOTE_STATE=str(remote.STORE))
        with (self.root / "worker.log").open("w") as log:
            process = subprocess.Popen([sys.executable, str(Path(app.__file__)), "_bridge", "demo"], env=env, stdout=log, stderr=log)
            db = remote.database()
            try:
                deadline = time.monotonic() + 10
                while not remote.worker_status(db, "demo")["online"]:
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail((self.root / "worker.log").read_text())
                    time.sleep(.1)
                result = subprocess.run([sys.executable, str(Path(remote.__file__)), "run", "--timeout", "10", "demo", "echo", "hello from cloud"],
                                        env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr + (self.root / "worker.log").read_text())
                self.assertEqual(result.stdout, "local-value:hello from cloud\n")
            finally:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
                db.close()


if __name__ == "__main__":
    unittest.main()
