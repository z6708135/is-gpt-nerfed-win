"""Private offline subprocess fixture. Never invokes Codex, shells or a network API.

Only tests/test_windows.py should start this file. All supplied paths must point
at that test's TemporaryDirectory; no user profile paths are used here.
"""
from __future__ import annotations

import importlib.util
import importlib.machinery
import builtins
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


def wait_for_file(path: Path, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"offline fixture timed out waiting for {path.name}")
        time.sleep(0.02)


def lock_fixture(args: list[str]) -> None:
    adapter_file, lock_file, acquired, release, counter = map(Path, args)
    spec = importlib.util.spec_from_file_location("offline_platform", adapter_file)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    acquired.with_suffix(".attempting").write_text(str(os.getpid()), encoding="utf-8")
    with adapter.exclusive_file_lock(str(lock_file)):
        acquired.write_text(str(os.getpid()), encoding="utf-8")
        wait_for_file(release)
        value = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
        counter.write_text(str(value + 1), encoding="utf-8")


def hold_fixture(args: list[str]) -> None:
    acquired, release = map(Path, args)
    acquired.write_text(str(os.getpid()), encoding="utf-8")
    wait_for_file(release)


def rpc_fixture(args: list[str]) -> None:
    """JSON-lines echo, with a request audit file for the no-active-turn test."""
    log_file = Path(args[0])
    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    for line in sys.stdin:
        message = json.loads(line)
        with log_file.open("a", encoding="utf-8") as log:
            log.write(json.dumps(message, ensure_ascii=False) + "\n")
        if "id" in message:
            result = message.get("params") or {}
            if message.get("method") == "initialize":
                result = {"userAgent": "offline Windows fixture"}
            print(json.dumps({"id": message["id"], "result": result}, ensure_ascii=False), flush=True)
        elif message.get("method") == "initialized":
            print(json.dumps({"method": "offline/ready", "params": {"text": "本地回声"}}, ensure_ascii=False), flush=True)


def guarded_hook(source: str, audit_file: str, fixture_root: str) -> None:
    """Run a temporary reviewed CLI copy with child-process safety spies installed.

    The real PowerShell adapter invokes this wrapper with its actual -I -B hook
    arguments. Spies persist swallowed violations so a fail-open hook cannot make
    a credential/process/network attempt look like a successful offline test.
    """
    root = Path(fixture_root).resolve()
    source_path, audit_path = Path(source).resolve(), Path(audit_file).resolve()
    for path in (source_path, audit_path, Path(os.environ["CODEX_HOME"]).resolve(),
                 Path(os.environ["NERFED_HOME"]).resolve()):
        if not path.is_relative_to(root):
            raise RuntimeError("offline hook fixture path escaped its temporary root")
    original_open, original_io_open = builtins.open, io.open

    def violation(kind):
        with original_open(audit_path, "a", encoding="utf-8") as audit:
            audit.write(json.dumps({"violation": kind}) + "\n")
        raise AssertionError("offline native hook fixture denied " + kind)

    def guarded_open(original):
        def checked(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)) and ("r" in mode or "+" in mode):
                if Path(os.fsdecode(file)).name.lower() == "auth.json":
                    violation("credential read")
            return original(file, mode, *args, **kwargs)
        return checked

    def no_process(*args, **kwargs):
        violation("external process")

    def no_network(*args, **kwargs):
        violation("network access")

    builtins.open = guarded_open(original_open)
    io.open = guarded_open(original_io_open)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        setattr(subprocess, name, no_process)
    os.system = os.popen = no_process
    socket.socket = socket.create_connection = no_network
    urllib.request.urlopen = no_network
    sys.path.insert(0, str(source_path.parent))
    loader = importlib.machinery.SourceFileLoader("offline_reviewed_hook", str(source_path))
    spec = importlib.util.spec_from_loader("offline_reviewed_hook", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    raise SystemExit(module.main(sys.argv[1:]))


if __name__ == "__main__":
    operation, *arguments = sys.argv[1:]
    {"lock": lock_fixture, "hold": hold_fixture, "rpc": rpc_fixture}[operation](arguments)
