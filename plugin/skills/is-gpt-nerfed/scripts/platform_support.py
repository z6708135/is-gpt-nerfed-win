"""Small OS adapters; importing this module does not launch commands or read sessions."""
from __future__ import annotations

import contextlib
import ctypes
import glob
import os
import subprocess
import sys
import time

IS_WINDOWS = os.name == "nt"


def configure_standard_streams() -> None:
    """Codex hook JSON and the Chinese CLI output use UTF-8 on Windows too."""
    if IS_WINDOWS:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")


def process_options(background: bool = False) -> dict:
    """Use native executables with no shell and no extra Windows console."""
    options = {"shell": False}
    if IS_WINDOWS:
        flags = subprocess.CREATE_NO_WINDOW
        if background:
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        options.update(creationflags=flags, close_fds=True)
    elif background:
        options["start_new_session"] = True
    return options


def pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False
    # os.kill(pid, 0) on Windows can terminate a process. Request QUERY access only.
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: conservatively still alive
    try:
        status = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(status))) and status.value == 259
    finally:
        kernel.CloseHandle(handle)


@contextlib.contextmanager
def exclusive_file_lock(path: str):
    """Lock byte zero on Windows, flock the whole file on POSIX."""
    with open(path, "a+b") as lock:
        if IS_WINDOWS:
            import msvcrt
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (11, 13, 36):
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def windows_codex_candidates(codex_home: str) -> list[str]:
    """Find native codex.exe files, never execute npm .cmd/.bat shell wrappers."""
    if not IS_WINDOWS:
        return []
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    program = os.environ.get("ProgramFiles", "")
    candidates = [os.path.join(codex_home, ".sandbox-bin", "codex.exe")]
    candidates += [os.path.join(p, "codex.exe") for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    patterns = []
    if local:
        patterns += [os.path.join(local, "Programs", app, rel, "codex.exe")
                     for app in ("Codex", "ChatGPT")
                     for rel in ("", "resources", "resources/codex-cli/bin")]
    if roaming:
        patterns += [os.path.join(roaming, "npm", "node_modules", "@openai", "codex", "vendor", "*", "codex", "codex.exe"),
                     os.path.join(roaming, "npm", "node_modules", "@openai", "codex-*", "vendor", "*", "codex", "codex.exe")]
    if program:
        patterns += [os.path.join(program, "WindowsApps", "OpenAI.*", rel, "codex.exe")
                     for rel in ("app/resources", "app/resources/codex-cli/bin", "resources", "resources/codex-cli/bin")]
    for pattern in patterns:
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    return candidates
