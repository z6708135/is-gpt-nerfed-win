"""Generate shell-safe Windows hook commands from the reviewed passive dispatcher.

Run this standard-library-only source tool after reviewing edits. --check compares the
manifest without writing it. This tool does not launch hooks, CLI processes or probes.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
from pathlib import Path

PORT_VERSION = "0.5.3-windows.2"
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd")
COMMAND_PREFIX = (
    "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden "
    "-ExecutionPolicy Bypass -EncodedCommand "
)

# Encoding protects $p, $s and $env from expansion by the outer Codex PowerShell
# command. The dispatch actions are unchanged. The first statement suppresses
# first-use module progress chatter so the hook transport receives only its JSON.
# The event is substituted only after the fixed allowlist check below.
DISPATCHER_TEMPLATE = (
    "& { $ProgressPreference = 'SilentlyContinue'; $p = $env:PLUGIN_ROOT; if (-not $p) { $p = $env:CLAUDE_PLUGIN_ROOT }; "
    "if (-not $p) { Write-Output '{}'; exit 0 }; "
    "$s = Join-Path $p 'skills/is-gpt-nerfed/scripts/hook-windows.ps1'; "
    "if (Test-Path -LiteralPath $s -PathType Leaf) { & $s -Event '__EVENT__' } "
    "else { Write-Output '{}' }; exit 0 }"
)


def dispatcher_for_event(event: str) -> str:
    if event not in EVENTS:
        raise ValueError(f"Unreviewed hook event: {event!r}")
    return DISPATCHER_TEMPLATE.replace("__EVENT__", event)


def encoded_command(event: str) -> str:
    data = dispatcher_for_event(event).encode("utf-16-le")
    return COMMAND_PREFIX + base64.b64encode(data).decode("ascii")


def build_manifest(manifest: dict) -> dict:
    """Change only the public port version and the five Windows dispatcher strings."""
    result = copy.deepcopy(manifest)
    hooks = result["hooks"]["hooks"]
    if set(hooks) != set(EVENTS):
        raise ValueError("The hook event set changed; review it before regenerating")
    for event in EVENTS:
        groups = hooks[event]
        if len(groups) != 1 or len(groups[0]["hooks"]) != 1:
            raise ValueError(f"The hook layout changed for {event}; review it before regenerating")
        hook = groups[0]["hooks"][0]
        if hook.get("type") != "command":
            raise ValueError(f"Expected a command hook for {event}")
        hook["commandWindows"] = encoded_command(event)
    result["version"] = PORT_VERSION
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "plugin" / ".codex-plugin" / "plugin.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    generated = build_manifest(current)
    if args.check:
        if current != generated:
            parser.exit(1, "Windows hook commands or version are stale; review and regenerate.\n")
        print("Windows hook commands match the reviewed dispatcher.")
        return 0
    path.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated plugin/.codex-plugin/plugin.json from the reviewed dispatcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
