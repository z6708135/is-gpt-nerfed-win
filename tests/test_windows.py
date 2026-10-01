"""Isolated Windows regressions: no real Codex, auth, network or user sessions.

Run only after approval, from the repository root:
    python -m unittest discover -s tests -p test_windows.py -v

Each case loads the CLI with fresh temporary CODEX_HOME/NERFED_HOME. Every
subprocess/network entry is denied by default, including attempts swallowed by
the production code. The only subprocess exception is this suite's own small
windows_test_helper.py fixture, launched with the current Python interpreter.
"""
from __future__ import annotations

import argparse
import base64
import builtins
from contextlib import ExitStack, redirect_stdout
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugin" / "skills" / "is-gpt-nerfed" / "scripts"
HELPER = Path(__file__).with_name("windows_test_helper.py").resolve()
MANIFEST = ROOT / "plugin" / ".codex-plugin" / "plugin.json"
POWERSHELL_PATH = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
PWSH_PATH = shutil.which("pwsh.exe") or shutil.which("pwsh")
OUTER_SHELLS = tuple(path.resolve() for path in (POWERSHELL_PATH, Path(PWSH_PATH) if PWSH_PATH else None)
                    if path is not None and path.is_file())
REAL_POPEN = subprocess.Popen
REAL_BUILTIN_OPEN = builtins.open
REAL_IO_OPEN = io.open
SID = "11111111-1111-4111-8111-111111111111"


def load_source(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def rollout(*models: str) -> str:
    return "".join(json.dumps({
        "type": "turn_context", "timestamp": f"2026-01-01T00:00:{index:02}Z",
        "payload": {"turn_id": str(index), "model": model,
                    "collaboration_mode": {"settings": {"reasoning_effort": "high"}}},
    }) + "\n" for index, model in enumerate(models))


@unittest.skipUnless(os.name == "nt", "native Windows regression suite")
class WindowsRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nerfed-windows-offline-")
        self.addCleanup(self.temporary.cleanup)
        self.tmp = Path(self.temporary.name)
        self.codex_home = self.tmp / "codex-home"
        self.nerfed_home = self.tmp / "nerfed-home"
        self.codex_home.mkdir()
        self.nerfed_home.mkdir()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.dict(os.environ, {
            "CODEX_HOME": str(self.codex_home), "NERFED_HOME": str(self.nerfed_home),
            "NERFED_NO_UPDATE_CHECK": "1", "PYTHONUTF8": "1",
            "PATH": "", "LOCALAPPDATA": str(self.tmp / "local"),
            "APPDATA": str(self.tmp / "roaming"), "ProgramFiles": str(self.tmp / "programs"),
            "PLUGIN_ROOT": str(ROOT / "plugin"),
        }))
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "NERFED_PROBE_PROCESS",
                     "CODEX_SANDBOX_NETWORK_DISABLED", "CLAUDE_PLUGIN_ROOT"):
            os.environ.pop(name, None)
        self.auth_reads = []
        self.forbidden_files = set()
        self.external_attempts = []
        self.network_attempts = []
        self.children = []
        self.addCleanup(self.stop_children)
        self.stack.enter_context(mock.patch.object(builtins, "open", self.checked_open(REAL_BUILTIN_OPEN)))
        self.stack.enter_context(mock.patch.object(io, "open", self.checked_open(REAL_IO_OPEN)))
        for name in ("Popen", "run", "call", "check_call", "check_output"):
            self.stack.enter_context(mock.patch.object(subprocess, name, self.deny_process))
        self.stack.enter_context(mock.patch.object(os, "system", self.deny_process))
        self.stack.enter_context(mock.patch.object(os, "popen", self.deny_process))
        self.stack.enter_context(mock.patch.object(socket, "socket", self.deny_network))
        self.stack.enter_context(mock.patch.object(socket, "create_connection", self.deny_network))
        self.stack.enter_context(mock.patch.object(urllib.request, "urlopen", self.deny_network))
        # Import is also guarded: future accidental top-level side effects fail this suite.
        self.stack.enter_context(mock.patch.object(sys, "path", [str(SCRIPTS), *sys.path]))
        self.dgc = load_source("offline_windows_nerfed", SCRIPTS / "nerfed")
        self.platform = self.dgc.platform
        self.cas = self.dgc.cas
        # A tempting fake credential fixture. A read of it is denied and recorded.
        (self.codex_home / "auth.json").write_text('{"OFFLINE_SENTINEL":"do not read"}', encoding="utf-8")

    def tearDown(self):
        self.assertEqual(self.auth_reads, [], "default path attempted to read auth.json")
        self.assertEqual(self.external_attempts, [], "default path attempted an external process")
        self.assertEqual(self.network_attempts, [], "default path attempted network access")

    def checked_open(self, original):
        def guarded(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(file)).resolve()
                reading = "r" in mode or "+" in mode
                if reading and path.name.lower() == "auth.json":
                    self.auth_reads.append(str(path))
                    raise AssertionError("the offline suite forbids credential reads")
                if reading and path in self.forbidden_files:
                    raise AssertionError("the offline suite forbids unrelated session reads")
            return original(file, mode, *args, **kwargs)
        return guarded

    def deny_process(self, *args, **kwargs):
        self.external_attempts.append(args[0] if args else kwargs.get("args"))
        raise AssertionError("only the dedicated offline Python helper may run")

    def deny_network(self, *args, **kwargs):
        self.network_attempts.append("network requested")
        raise AssertionError("offline Windows regressions forbid network access")

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=5)
            finally:
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream is not None:
                        stream.close()

    def start_helper(self, operation: str, *paths: Path, **options):
        self.assertIn(operation, ("lock", "hold", "rpc"))
        for path in paths:
            # The sole read-only exception is the OS adapter needed by the lock fixture.
            if operation == "lock" and path == SCRIPTS / "platform_support.py":
                continue
            self.assertTrue(path.resolve().is_relative_to(self.tmp.resolve()), str(path))
        command = [sys.executable, "-I", str(HELPER), operation, *map(str, paths)]
        options.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        options.setdefault("shell", False)
        child = REAL_POPEN(command, **options)
        self.children.append(child)
        return child

    def start_outer_shell_fixture(self, executable: Path, command: str, fixture_root: Path,
                                  plugin_root: Path, **environment):
        self.assertIn(executable.resolve(), OUTER_SHELLS)
        self.assertTrue(fixture_root.resolve().is_relative_to(self.tmp.resolve()))
        self.assertTrue(plugin_root.resolve().is_relative_to(fixture_root.resolve()))
        commands = {hook["commandWindows"]
                    for entries in json.loads(MANIFEST.read_text(encoding="utf-8"))["hooks"]["hooks"].values()
                    for entry in entries for hook in entry["hooks"]}
        self.assertIn(command, commands, "only an exact reviewed manifest command may run")
        env = {**os.environ, **environment, "PLUGIN_ROOT": str(plugin_root),
               "CLAUDE_PLUGIN_ROOT": "", "PATH": str(POWERSHELL_PATH.parent),
               "NERFED_NO_UPDATE_CHECK": "1", "PYTHONUTF8": "1"}
        child = REAL_POPEN([str(executable), "-NoProfile", "-NonInteractive", "-Command", command],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", errors="replace", env=env,
                           shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        self.children.append(child)
        return child

    def wait_file(self, path: Path, child=None, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while not path.exists():
            if child is not None and child.poll() is not None:
                self.fail(f"offline helper exited before producing {path.name}: {child.returncode}")
            if time.monotonic() >= deadline:
                self.fail(f"offline helper timed out waiting for {path.name}")
            time.sleep(0.02)

    def cli(self, *argv: str):
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.dgc.main(list(argv))
        return result, output.getvalue()

    def hook(self, event: str, **payload):
        data = {"hook_event_name": event, "thread_id": SID, "cwd": str(self.tmp), **payload}
        output = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))), redirect_stdout(output):
            # Use the entrypoint without main's fail-open wrapper, so defects are visible.
            result = self.dgc.cmd_hook(argparse.Namespace(event=None))
        self.assertEqual(result, 0)
        text = output.getvalue().strip()
        return json.loads(text) if text else {}

    def no_discovery(self):
        stack = ExitStack()
        for name in ("db_recent_main_thread", "db_recent_main_threads", "db_recent_threads_detailed"):
            stack.enter_context(mock.patch.object(self.dgc, name,
                                side_effect=AssertionError("broad session discovery is forbidden")))
        return stack

    def test_windows_defaults_disable_every_sensitive_opt_in(self):
        cfg = self.dgc.load_config()
        for key in ("active_probes", "background_probes", "auto_retries", "account_metadata",
                    "discover_sessions", "check_updates", "notify", "sound", "halt_on_mismatch"):
            with self.subTest(key=key):
                self.assertIs(cfg[key], False)
        self.assertEqual(cfg["frequency"], "manual")
        self.assertEqual(cfg["fresh_frequency"], "manual")
        self.assertTrue(cfg["passive"])

    def test_account_helpers_do_not_open_credentials(self):
        account = self.dgc.current_account()
        self.assertEqual(account["id"], self.dgc.UNKNOWN_ACCOUNT)
        self.assertIsNone(account["plan"])
        self.assertEqual(self.dgc.note_account("offline test")["id"], self.dgc.UNKNOWN_ACCOUNT)

    def test_default_passive_commands_have_no_auth_network_or_process_side_effects(self):
        commands = [("config",), ("status",), ("report",), ("snapshot",),
                    ("doctor", "--no-cli"), ("hooks", "status"), ("log",), ("explain", "--method")]
        for command in commands:
            with self.subTest(command=command):
                if command[0] == "hooks":
                    # Explicit hooks status needs a server metadata response; fake that read-only API.
                    with mock.patch.object(self.dgc, "codex_bin", return_value="OFFLINE_TEST_FIXTURE"), \
                            mock.patch.object(self.cas, "list_plugin_hooks", return_value={"hooks": [], "notes": []}):
                        result, _ = self.cli(*command)
                else:
                    result, _ = self.cli(*command)
                self.assertIn(result, (0, 1), "doctor may report an intentionally absent Codex binary")

    def test_default_active_cli_entries_reject_before_starting_inference(self):
        commands = [("probe", "now", "--thread", SID), ("probe", "now", "--thread", SID, "--mode", "self"),
                    ("probe", "fresh"), ("probe", "submit-numbers", "offline-only", "--numbers", "[1,2,3]"),
                    ("worker", "--thread", SID), ("worker", "--fresh"), ("update-check",)]
        for command in commands:
            with self.subTest(command=command), self.assertRaisesRegex(SystemExit, "disabled|approval"):
                self.cli(*command)
        self.assertEqual(list((self.nerfed_home / "probes").glob("*.json")), [])

    def test_low_level_cli_active_entries_also_reject(self):
        cfg = self.dgc.load_config()
        calls = [lambda: self.dgc.run_fork_probe(SID, cfg),
                 lambda: self.dgc.run_fresh_probe(cfg, model="gpt-6-astra"),
                 lambda: self.dgc.start_self_probe(SID, "offline-side", cfg, "gpt-6-astra")]
        for index, call in enumerate(calls):
            with self.subTest(entry=index), self.assertRaisesRegex(SystemExit, "disabled|approval"):
                call()

    def test_default_scheduler_cannot_spawn_even_when_a_probe_is_requested(self):
        cfg = {**self.dgc.load_config(), "mode": "auto", "frequency": "1m", "fresh_frequency": "1m"}
        session = self.dgc.new_session(SID)
        session.update(kind="main", requested=True, turns=100, created_ts=0)
        self.assertFalse(self.dgc.probe_due(session, cfg))
        self.assertFalse(self.dgc.fresh_due(cfg, self.dgc.UNKNOWN_ACCOUNT))
        self.assertFalse(self.dgc.spawn_worker(SID, cfg))
        self.assertFalse(self.dgc.spawn_fresh_worker())
        self.assertFalse(self.dgc.run_schedule(session, cfg, self.dgc.current_account(), []))
        self.assertEqual(self.cli("tick")[0], 0)

    def test_hooks_scan_only_the_payload_session(self):
        sessions = self.codex_home / "sessions"
        sessions.mkdir()
        current = sessions / f"rollout-{SID}.jsonl"
        header = json.dumps({"type": "session_meta", "payload": {"id": SID}}) + "\n"
        current.write_text(header + rollout("gpt-6-astra", "gpt-5.5"), encoding="utf-8")
        other_sid = "22222222-2222-4222-8222-222222222222"
        unrelated = sessions / f"rollout-{other_sid}.jsonl"
        unrelated.write_text(json.dumps({"type": "session_meta", "payload": {"id": other_sid}}) + "\n"
                             + rollout("gpt-6-astra", "gpt-reserve"), encoding="utf-8")
        self.forbidden_files.add(unrelated.resolve())
        with self.no_discovery(), mock.patch.object(self.dgc, "db_thread", return_value=None) as lookup, \
                mock.patch.object(self.dgc, "scan_rollout", wraps=self.dgc.scan_rollout) as scan:
            for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd"):
                self.hook(event, model="gpt-6-astra", transcript_path=str(current), tool_name="offline_tool")
            self.assertTrue(scan.called)
            # Windows realpath expands 8.3 aliases in TEMP; compare file identity.
            self.assertTrue(all(os.path.samefile(call.args[0], current) for call in scan.call_args_list),
                            [call.args[0] for call in scan.call_args_list])
            self.assertTrue(all(call.args == (SID,) for call in lookup.call_args_list))
        state = self.dgc.load_session(SID)
        self.assertEqual(state["scan"]["models_seen"], {"gpt-6-astra": 1, "gpt-5.5": 1})
        self.assertTrue(any(item["kind"] == "silent_model_change" for item in state["evidence"]))

    def test_hooks_without_a_current_path_never_guess_another_session(self):
        with self.no_discovery(), mock.patch.object(self.dgc, "db_thread", return_value=None), \
                mock.patch.object(self.dgc, "scan_rollout", wraps=self.dgc.scan_rollout) as scan:
            self.hook("Stop")
            scan.assert_not_called()
            self.assertEqual(self.dgc.resolve_thread(None)[0], None)

    def test_default_tool_hooks_do_not_persist_secret_tool_input(self):
        secret = "offline-secret-54ca8bb9-token"
        with self.no_discovery(), mock.patch.object(self.dgc, "db_thread", return_value=None):
            self.hook("PreToolUse", tool_name="exec_command", tool_input={
                "cmd": f"offline-tool --token {secret}", "headers": {"Authorization": secret},
            })
        for path in self.nerfed_home.rglob("*"):
            if path.is_file() and path.suffix != ".lock":
                with self.subTest(path=path.name):
                    self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_audit_is_opt_in_and_doctor_fork_requires_active_approval(self):
        for command in (("audit",), ("doctor", "--fork", "--thread", SID)):
            with self.subTest(command=command), self.assertRaisesRegex(SystemExit, "disabled|approval"):
                self.cli(*command)

    def test_match_needs_probability_margin_competitor_and_two_answers(self):
        def analysis(probability=0.9, runner_probability=0.1, margin=0.6, answers=2, competitor=True):
            rows = [{"model": "gpt-6-astra", "probability": probability, "score": 1.0}]
            if competitor:
                rows.append({"model": "gpt-5.5", "probability": runner_probability, "score": 1.0 - margin})
            return {"results": rows, "used_outputs": answers}
        cases = [analysis(probability=0.51, runner_probability=0.49), analysis(margin=0.49),
                 analysis(answers=1), analysis(answers=0), analysis(competitor=False)]
        for sample in cases:
            with self.subTest(sample=sample):
                verdict = self.dgc.assess("gpt-6-astra", sample, [], self.dgc.load_config())
                self.assertEqual(verdict["verdict"], "SUSPICIOUS")
                self.assertEqual(verdict["confidence"], "low")
        self.assertEqual(self.dgc.assess("gpt-6-astra", analysis(), [], {})["verdict"], "MATCH")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("do not prove model identity", manifest["description"])

    def test_windows_pid_check_never_terminates_a_live_helper(self):
        ready, release = self.tmp / "pid-ready", self.tmp / "pid-release"
        child = self.start_helper("hold", ready, release)
        self.wait_file(ready, child)
        with mock.patch.object(self.platform.os, "kill", side_effect=AssertionError("pid checks must not call os.kill")):
            for _ in range(10):
                self.assertTrue(self.platform.pid_alive(child.pid))
                self.assertIsNone(child.poll())
            for invalid in (None, "bad", 0, -1):
                self.assertFalse(self.platform.pid_alive(invalid))
        release.write_text("release", encoding="utf-8")
        self.assertEqual(child.wait(timeout=5), 0)
        self.assertFalse(self.platform.pid_alive(child.pid))

    def test_native_file_lock_serializes_independent_processes_and_releases(self):
        lock, counter = self.tmp / "session.lock", self.tmp / "counter"
        ready1, ready2 = self.tmp / "ready1", self.tmp / "ready2"
        release1, release2 = self.tmp / "release1", self.tmp / "release2"
        first = self.start_helper("lock", SCRIPTS / "platform_support.py", lock, ready1, release1, counter)
        self.wait_file(ready1, first)
        release2.write_text("release", encoding="utf-8")
        second = self.start_helper("lock", SCRIPTS / "platform_support.py", lock, ready2, release2, counter)
        self.wait_file(ready2.with_suffix(".attempting"), second)
        time.sleep(0.2)
        self.assertFalse(ready2.exists(), "the second process acquired a held lock")
        self.assertIsNone(second.poll())
        release1.write_text("release", encoding="utf-8")
        self.assertEqual(first.wait(timeout=5), 0)
        self.wait_file(ready2, second)
        self.assertEqual(second.wait(timeout=5), 0)
        self.assertEqual(counter.read_text(encoding="utf-8"), "2")

    def test_native_lock_recovers_after_its_owner_process_dies(self):
        lock, counter = self.tmp / "crash.lock", self.tmp / "counter"
        ready1, ready2 = self.tmp / "ready1", self.tmp / "ready2"
        release1, release2 = self.tmp / "never-release", self.tmp / "release2"
        first = self.start_helper("lock", SCRIPTS / "platform_support.py", lock, ready1, release1, counter)
        self.wait_file(ready1, first)
        first.terminate()  # Only the dedicated test-owned helper is terminated.
        first.wait(timeout=5)
        release2.write_text("release", encoding="utf-8")
        second = self.start_helper("lock", SCRIPTS / "platform_support.py", lock, ready2, release2, counter)
        self.wait_file(ready2, second)
        self.assertEqual(second.wait(timeout=5), 0)
        self.assertEqual(counter.read_text(encoding="utf-8"), "1")

    def test_windows_threaded_pipe_handles_utf8_without_select_and_refuses_active_requests(self):
        rpc_log = self.tmp / "rpc.jsonl"
        captured_options = []
        def fixture_popen(args, **options):
            self.assertEqual(args[0], "OFFLINE_TEST_FIXTURE")
            self.assertEqual(args[1:3], ["app-server", "--stdio"])
            captured_options.append(options.copy())
            return self.start_helper("rpc", rpc_log, **options)
        with mock.patch.object(self.cas.subprocess, "Popen", fixture_popen):
            app = self.cas.AppServer("OFFLINE_TEST_FIXTURE")
        try:
            self.assertEqual(app.initialize()["userAgent"], "offline Windows fixture")
            echo = app.request("offline/echo", {"text": "离线管道 🧪"}, timeout=3)
            self.assertEqual(echo, {"text": "离线管道 🧪"})
            for method in ("thread/fork", "thread/start", "turn/start"):
                with self.subTest(method=method), self.assertRaises(self.cas.AppServerError):
                    app.request(method, {"threadId": SID}, timeout=0.2)
        finally:
            app.close()
            app._reader.join(timeout=3)
        self.assertFalse(app._reader.is_alive())
        self.assertIs(captured_options[0]["shell"], False)
        self.assertEqual(captured_options[0]["encoding"], "utf-8")
        self.assertTrue(captured_options[0]["creationflags"] & subprocess.CREATE_NO_WINDOW)
        methods = [json.loads(line)["method"] for line in rpc_log.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(set(methods) & {"thread/fork", "thread/start", "turn/start"})
        # Windows anonymous pipes are not select-able; the implementation must use its reader thread.
        self.assertNotIn("select.select", (SCRIPTS / "codex_appserver.py").read_text(encoding="utf-8"))

    def test_appserver_low_level_active_helpers_default_to_denial(self):
        calls = [lambda: self.cas.probe_thread("FORBIDDEN_REAL_CODEX", SID),
                 lambda: self.cas.probe_fresh("FORBIDDEN_REAL_CODEX", "gpt-6-astra"),
                 lambda: self.cas.fork_doctor("FORBIDDEN_REAL_CODEX", SID)]
        for index, call in enumerate(calls):
            with self.subTest(entry=index), self.assertRaises(self.cas.AppServerError):
                call()

    def test_each_manifest_hook_has_a_hidden_native_windows_command(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        generator = load_source("offline_windows_hooks_generator", ROOT / "tools" / "build_windows_hooks.py")
        self.assertEqual(manifest["version"], generator.PORT_VERSION)
        events = manifest["hooks"]["hooks"]
        self.assertEqual(set(events), {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd"})
        for event, entries in events.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    command = hook["commandWindows"]
                    with self.subTest(event=event):
                        self.assertIn("powershell.exe", command)
                        self.assertIn("-NoProfile", command)
                        self.assertIn("-NonInteractive", command)
                        self.assertIn("-WindowStyle Hidden", command)
                        self.assertIn("-ExecutionPolicy Bypass", command)
                        match = re.search(r" -EncodedCommand ([A-Za-z0-9+/=]+)$", command)
                        self.assertIsNotNone(match)
                        dispatcher = base64.b64decode(match.group(1), validate=True).decode("utf-16-le")
                        self.assertEqual(dispatcher, generator.dispatcher_for_event(event))
                        self.assertEqual(command, generator.encoded_command(event))
                        self.assertIn("$env:PLUGIN_ROOT", dispatcher)
                        self.assertIn("$env:CLAUDE_PLUGIN_ROOT", dispatcher)
                        self.assertIn("-LiteralPath", dispatcher)
                        self.assertIn("hook-windows.ps1", dispatcher)
                        self.assertIn(f"-Event '{event}'", dispatcher)
                        self.assertNotIn("sh -c", command)
                        self.assertNotIn("auth.json", dispatcher)
                        self.assertNotIn("codex.exe", dispatcher)
        with self.assertRaises(ValueError):
            generator.encoded_command("Stop'; Start-Process codex.exe; #")
        self.assertTrue((SCRIPTS / "hook-windows.ps1").is_file())

    def test_manifest_commands_work_through_real_outer_powershell_with_passive_fixtures(self):
        if not POWERSHELL_PATH.is_file():
            self.skipTest("Windows PowerShell is unavailable")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        event_order = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd")
        for shell_index, shell in enumerate(OUTER_SHELLS):
            with self.subTest(outer_shell=shell.name):
                fixture_root = self.tmp / f"outer shell {shell_index} spaces ' $p"
                fixture_root.mkdir()
                plugin = fixture_root / "copied plugin"
                shutil.copytree(ROOT / "plugin", plugin, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                script_dir = plugin / "skills" / "is-gpt-nerfed" / "scripts"
                codex_home, state_home = fixture_root / "codex-home", fixture_root / "nerfed-home"
                codex_home.mkdir()
                state_home.mkdir()
                sessions = codex_home / "sessions"
                sessions.mkdir()
                transcript = sessions / f"rollout-{SID}.jsonl"
                transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": SID}}) + "\n"
                                      + rollout("gpt-6-astra", "gpt-5.5"), encoding="utf-8")
                safe_cfg = {key: False for key in ("active_probes", "background_probes", "auto_retries",
                            "account_metadata", "discover_sessions", "record_tool_commands", "check_updates",
                            "notify", "sound", "halt_on_mismatch")}
                safe_cfg.update(frequency="manual", fresh_frequency="manual", mode="nudge", passive=True,
                                codex_bin=None)
                (state_home / "config.json").write_text(json.dumps(safe_cfg), encoding="utf-8")
                (codex_home / "auth.json").write_text('{"OFFLINE_SENTINEL":"never read"}', encoding="utf-8")
                runtime = {"pythonPath": sys.executable, "codexHome": str(codex_home), "nerfedHome": str(state_home)}
                (script_dir / "windows-runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
                # Preserve the reviewed CLI byte-for-byte and add spies only in a temporary entry wrapper.
                reviewed_source = script_dir / "nerfed-reviewed-source"
                (script_dir / "nerfed").rename(reviewed_source)
                shutil.copyfile(HELPER, script_dir / "windows_test_helper.py")
                audit = fixture_root / "safety-audit.jsonl"
                wrapper = ("import os, sys\n"
                           "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                           "from windows_test_helper import guarded_hook\n"
                           f"guarded_hook({str(reviewed_source)!r}, {str(audit)!r}, {str(fixture_root)!r})\n")
                (script_dir / "nerfed").write_text(wrapper, encoding="utf-8")
                # An inherited configuration must not override adapter runtime homes.
                decoy_codex, decoy_state = fixture_root / "decoy-codex", fixture_root / "decoy-state"
                decoy_codex.mkdir()
                decoy_state.mkdir()
                (decoy_codex / "auth.json").write_text('{"OFFLINE_SENTINEL":"wrong home"}', encoding="utf-8")
                (decoy_state / "config.json").write_text(json.dumps({"account_metadata": True,
                    "active_probes": True, "background_probes": True, "mode": "auto", "frequency": "1m"}), encoding="utf-8")
                secret = "offline-wrapper-secret-20a3"
                outputs = {}
                for event in event_order:
                    hook = manifest["hooks"]["hooks"][event][0]["hooks"][0]
                    command = hook["commandWindows"]
                    child = self.start_outer_shell_fixture(shell, command, fixture_root, plugin,
                                                           CODEX_HOME=str(decoy_codex), NERFED_HOME=str(decoy_state))
                    payload = {"hook_event_name": event, "thread_id": SID, "cwd": str(fixture_root),
                               "transcript_path": str(transcript), "model": "gpt-6-astra",
                               "tool_name": "exec_command", "tool_input": {"cmd": f"unused-tool --token {secret}"}}
                    stdout, stderr = child.communicate(json.dumps(payload) + "\n", timeout=20)
                    self.assertEqual(child.returncode, 0, f"{shell.name}/{event}: {stderr}")
                    self.assertEqual(stderr.strip(), "", f"{shell.name}/{event}: {stderr}")
                    outputs[event] = json.loads(stdout.strip().lstrip("\ufeff"))
                events = [json.loads(line) for line in (state_home / "events.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual([entry["event"] for entry in events], list(event_order))
                self.assertTrue(all(entry["sid"] == SID for entry in events))
                state = json.loads((state_home / "sessions" / f"{SID}.json").read_text(encoding="utf-8"))
                self.assertEqual(state["turns"], 1)
                self.assertIsNotNone(state["ended"])
                self.assertEqual(state["scan"]["models_seen"], {"gpt-6-astra": 1, "gpt-5.5": 1})
                self.assertTrue(any(entry["kind"] == "silent_model_change" for entry in state["evidence"]))
                self.assertIn("systemMessage", outputs["Stop"])
                self.assertEqual(state["probes"], [])
                self.assertEqual(list((state_home / "probes").glob("*.json")), [])
                self.assertFalse(audit.exists(), "native hook attempted credentials, a process or network access")
                self.assertEqual({entry.name for entry in decoy_state.iterdir()}, {"config.json"})
                for path in state_home.rglob("*"):
                    if path.is_file() and path.suffix != ".lock":
                        self.assertNotIn(secret, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
