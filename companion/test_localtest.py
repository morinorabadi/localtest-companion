"""Behavior checks, with real Mutagen integration when LOCALTEST_TEST_MUTAGEN is set."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import io
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("localtest", Path(__file__).with_name("localtest.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class Profiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = patch.object(app, "CONFIG", self.root / "config")
        self.state = patch.object(app, "STATE", self.root / "state")
        self.config.start()
        self.state.start()

    def tearDown(self):
        self.config.stop()
        self.state.stop()
        self.temp.cleanup()

    def add(self, name, **overrides):
        args = dict(name=name, workspace="dev", host=None, remote="/cloud/" + name,
                    local=str(self.root / name), port=None, setup="",
                    start="python3 -m http.server $PORT", stop="", restart_on_change=False,
                    url=None, ignore=[])
        args.update(overrides)
        app.add(argparse.Namespace(**args))
        return app.load(name)

    def test_projects_have_distinct_ports_folders_env_and_compose_names(self):
        a, b = self.add("first"), self.add("second")
        self.assertNotEqual(a["port"], b["port"])
        self.assertNotEqual(a["local_path"], b["local_path"])
        self.assertNotEqual(a["env_file"], b["env_file"])
        Path(a["env_file"]).write_text("TOKEN='first project'\nLITERAL=$(touch /tmp/should-not-run)\n")
        ea, eb = app.project_env(a), app.project_env(b)
        self.assertEqual(ea["TOKEN"], "first project")
        self.assertNotIn("TOKEN", eb)
        self.assertEqual(ea["LITERAL"], "$(touch /tmp/should-not-run)")
        self.assertNotEqual(ea["COMPOSE_PROJECT_NAME"], eb["COMPOSE_PROJECT_NAME"])

    def test_refuses_nonempty_or_overlapping_mirrors(self):
        a = self.add("first")
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.add("second", local=str(Path(a["local_path"]) / "nested"))
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "my-file").write_text("keep")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.add("third", local=str(occupied))

    def test_duplicate_ports_are_rejected_and_frontend_port_is_explicit(self):
        p = self.add("first", port=7088)
        with self.assertRaisesRegex(ValueError, "reserved"):
            self.add("second", port=7088)
        with patch.dict(os.environ, {"PORT": "9999"}):
            self.assertEqual(app.project_env(p)["PORT"], "7088")
            self.assertEqual(os.environ["PORT"], "9999")

    def test_failed_setup_does_not_run_stop_command(self):
        p = self.add("first", setup="setup-app", stop="stop-app")
        with patch.object(app, "ensure_sync"), patch.object(app.signal, "signal"), \
                patch.object(app, "shell", side_effect=ValueError("setup failed")) as shell:
            with self.assertRaisesRegex(ValueError, "setup failed"):
                app.service_run(p)
        shell.assert_called_once_with("setup-app", p)

    def test_cleanup_failure_preserves_startup_error(self):
        p = self.add("first", stop="stop-app")
        Path(p["local_path"]).mkdir()
        original = subprocess.CalledProcessError(23, ["start-app"])
        stderr = io.StringIO()
        with patch.object(app, "ensure_sync"), patch.object(app.signal, "signal"), \
                patch.object(app.subprocess, "Popen", side_effect=original), \
                patch.object(app, "shell", side_effect=ValueError("cleanup failed")), \
                patch.object(app.sys, "stderr", stderr):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                app.service_run(p)
        self.assertIs(raised.exception, original)
        self.assertIn("cleanup failed", stderr.getvalue())


    def test_changes_ignore_dependencies_but_detect_deletions(self):
        root = self.root / "source"
        (root / "node_modules").mkdir(parents=True)
        file = root / "app.py"
        file.write_text("print('hello')")
        before = app.source_stamp(root)
        (root / "node_modules" / "noise").write_text("new")
        self.assertEqual(before, app.source_stamp(root))
        file.unlink()
        self.assertNotEqual(before, app.source_stamp(root))

    def test_ssh_timeout_is_set_on_shared_daemon(self):
        p = self.add("first")
        with patch.object(app, "require"), patch.object(app, "run"), \
                patch.object(Path, "home", return_value=self.root), \
                patch.object(app.shutil, "which", return_value="/usr/bin/mutagen"):
            app.start(p)
        units = self.root / ".config/systemd/user"
        self.assertIn("Environment=MUTAGEN_SSH_CONNECT_TIMEOUT=60", (units / "localtest-sync.service").read_text())
        self.assertNotIn("MUTAGEN_SSH_CONNECT_TIMEOUT", (units / "localtest-first.service").read_text())


@unittest.skipUnless(os.environ.get("LOCALTEST_TEST_MUTAGEN"), "Set LOCALTEST_TEST_MUTAGEN to run actual sync")
class RealSync(unittest.TestCase):
    def test_cloud_to_local_changes_deletes_and_local_secrets_protected(self):
        binary = os.environ["LOCALTEST_TEST_MUTAGEN"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            alpha, beta = root / "cloud", root / "local"
            alpha.mkdir()
            beta.mkdir()
            env = dict(os.environ, MUTAGEN_DATA_DIRECTORY=str(root / "daemon"))
            def mutagen(*args):
                return subprocess.run([binary, *args], env=env, check=True, capture_output=True, text=True, timeout=30)
            (alpha / "app.txt").write_text("v1")
            (alpha / ".env.local").write_text("cloud-secret")
            (alpha / ".env.example").write_text("EXAMPLE=yes")
            generated = beta / "server/src/generated/prisma"
            generated.mkdir(parents=True)
            (generated / "client.ts").write_text("local-generated")
            (beta / ".env.local").write_text("local-secret")
            (beta / "node_modules").mkdir()
            (beta / "node_modules/keep").write_text("dependency")
            try:
                mutagen("daemon", "start")
                args = ["sync", "create", "--name", "test", "--no-global-configuration", "--sync-mode", "one-way-replica", "--ignore-vcs"]
                for pattern in app.BASE_IGNORES:
                    args += ["--ignore", pattern]
                mutagen(*args, str(alpha), str(beta))
                listed = mutagen("sync", "list", '--template={{range .}}{{.Name}}{{"\\n"}}{{end}}').stdout.splitlines()
                self.assertIn("test", listed)
                mutagen("sync", "flush", "test")
                self.assertEqual((beta / "app.txt").read_text(), "v1")
                self.assertEqual((beta / ".env.local").read_text(), "local-secret")
                self.assertTrue((beta / ".env.example").exists())
                self.assertTrue((beta / "node_modules/keep").exists())
                self.assertTrue((generated / "client.ts").exists())
                (alpha / "app.txt").write_text("v2")
                mutagen("sync", "flush", "test")
                self.assertEqual((beta / "app.txt").read_text(), "v2")
                (alpha / "app.txt").unlink()
                mutagen("sync", "flush", "test")
                self.assertFalse((beta / "app.txt").exists())
            finally:
                mutagen("daemon", "stop")


if __name__ == "__main__":
    unittest.main()
