# Windows port: scope, attribution, and validation

This Windows port is based on **kiyoakii's [is-gpt-nerfed](https://github.com/kiyoakii/is-gpt-nerfed)** at commit [`ff0d7c0c8fdc8713273b6570b1ada1838eaad84c`](https://github.com/kiyoakii/is-gpt-nerfed/tree/ff0d7c0c8fdc8713273b6570b1ada1838eaad84c). Its plugin version is `0.5.3-windows.2`. The Windows changes are separate contributions; they are not an official Windows release by the upstream author. The original macOS application and its installation instructions remain upstream material.

Release `0.5.3-windows.2` adds shell-safe encoding to the reviewed Windows hook dispatcher and suppresses PowerShell's first-use module progress chatter. Its dispatch actions and permissions are unchanged. The readable source and deterministic generator are in [tools/build_windows_hooks.py](../tools/build_windows_hooks.py). Editing this source does not update an existing `0.5.3-windows.1` installation or its trusted hook hashes. Offline synthetic hook checks do not establish that a hook fired naturally in a live Codex session.

The Windows integration covers the native Codex CLI and the Windows desktop conversation validated below. Actual command-hook arrivals establish execution for that tested desktop path; a local project directory, desktop originator, or backend version alone would not establish it. Other client versions and orchestration modes require their own validation. OpenAI documents that [cloud-orchestrated ChatGPT Work does not support plugin or local command hooks](https://learn.chatgpt.com/docs/enterprise/agent-security), even when tools execute on the local computer. Manual passive scans and offline command tests remain separate from natural hook-dispatch evidence.

## Current validation status

All 20 isolated tests passed: 18 Windows regressions and 2 calculation-parity checks. Five hook commands passed through real outer Windows PowerShell 5.1 and pwsh using synthetic session data. The passive scanner also read an explicitly selected real local session without starting inference or fingerprint probes. The reviewed installation has five enabled, trusted definitions; trust metadata is separate from execution evidence.

### Native CLI test

A user-run ordinary, read-only turn in Codex CLI 0.159.2 naturally dispatched SessionStart, UserPromptSubmit, Stop, and SessionEnd once each. The matching session state records one passively scanned turn and an ended session, with zero probes or alerts. That CLI turn made no tool calls, so it did not exercise PreToolUse. Its four real records were counted separately from five earlier synthetic records.

### Windows desktop test

A subsequent new chat in Windows Codex Desktop **26.928.4866.0**, using plugin **0.5.3-windows.2** and backend CLI **0.159.2**, completed one ordinary turn with one non-recursive, read-only directory-listing tool call. The selected session metadata identifies Codex Desktop; its events point to the installed `.2` plugin cache, establishing runtime loading rather than merely a disk registration.

| Desktop evidence | Observed result |
| --- | --- |
| SessionStart | 1 natural event |
| UserPromptSubmit | 1 natural event |
| PreToolUse | 1 natural event for the real tool call |
| Stop | 1 natural event |
| Passive analysis | 1 scanned turn and 1 recorded tool call; 0 probes and 0 alerts |
| Tool result | A matching tool return exists and the turn completed; the process exit code was not retained in the rollout |
| SessionEnd | Not observed; the session had not ended in the captured state |
| GUI plugin list | Not inspected visually; runtime loading is confirmed by the actual plugin events |

These four desktop records were separated from the earlier CLI and synthetic records. This verifies automatic passive hooks and the real PreToolUse path for the tested desktop conversation. It does not establish desktop SessionEnd, GUI list visibility, every other desktop mode/version, or a process exit code. The missing SessionEnd while the chat remained active is not a failure. Hook exit-code metadata was also absent from the rollout.

Active fingerprint probes remained disabled, and verification created no additional model turn. Public results retain only client/plugin versions, event names, counts, and verification limits; no local paths, project/chat names, session IDs, conversation bodies, logs, or private configuration are published. Recorded model metadata and statistical matches do not prove server-side model identity. Users must review and trust definitions in their own installations. Cloud-orchestrated dot command hooks remain unsupported.

## Attribution and license

- The upstream [MIT LICENSE](../LICENSE), including its copyright notice, is retained unchanged. Preserve upstream Git history when distributing the port.
- ModelTrace data and scoring references come from **xqy2006's [ModelTrace](https://github.com/xqy2006/ModelTrace)**. Its [license](../plugin/assets/modeltrace/LICENSE-ModelTrace.txt), [provenance](../plugin/assets/modeltrace/provenance.json), and fingerprint bank remain unchanged. The recorded data revision is `55a2e4a55170423b484d701e9a82ab62b268c811`. See the provenance file for the scorer and ModelTraceGuard prompt credits.
- The vendored [simple-term-menu license](../plugin/skills/is-gpt-nerfed/scripts/vendor/LICENSE-simple-term-menu.txt) is retained unchanged.

No upstream copyright or third-party attribution is replaced by the Windows documentation.

## Changes and limits

The port adds native PowerShell install/uninstall and CLI wrappers, Windows hook commands, Windows file locking, and process checks that do not use `os.kill(pid, 0)`. It uses native executables, UTF-8 data, and hidden subprocess windows, and preserves existing `CODEX_SANDBOX*` restrictions.

Windows defaults are passive: active probes, background probes, automatic retries, account metadata, session discovery, tool command recording, and update checks are disabled. The installer creates a dedicated `is-gpt-nerfed-windows` marketplace and the plugin ID `is-gpt-nerfed@is-gpt-nerfed-windows`; it neither trusts hooks automatically nor starts a daemon. Existing plugins and settings are inspected and preserved. Managed uninstall verifies its recorded scope, removes those registrations, and archives its own files while retaining evidence and backups.

Hooks inspect only an explicitly identified local session. A Windows rollout must resolve inside the configured `CODEX_HOME/sessions`, be a `.jsonl` file whose name contains the full session ID, and have a matching `session_meta.payload.id` header. Missing or mismatched inputs are skipped. There is no default fallback to recent or unrelated sessions.

The macOS menu-bar application, notifications, and macOS installer/updater are not ported. Development used the native Windows Codex CLI `0.159.2` with a valid `OpenAI OpCo, LLC` Authenticode signature. Other versions and storage layouts need their own verification. Python 3 is required; a directory name is not evidence of its exact version.

OpenAI's [hooks documentation](https://learn.chatgpt.com/docs/hooks) describes `commandWindows` and content-hash trust. Its [plugins documentation](https://learn.chatgpt.com/docs/plugins) states that plugin hooks are not supported in cloud-orchestrated ChatGPT Work. A local installation does not establish that dot cloud conversations can load these scripts or that their model metadata is visible locally.

## Privacy and active functionality

Passive evidence can contain session IDs, working directories, rollout paths, timestamps, model settings, prompt lengths, and tool names. Command text is omitted by default, but reading a selected rollout necessarily reads its contents. Title hiding is a presentation setting, not anonymization. Runtime files, evidence, installation journals, and configuration backups are private local data.

The plugin's credential-reading entry point returns an unknown account unless `account_metadata` is explicitly `true`. This is a program guard rather than an operating-system access boundary. Keep it disabled for passive use; the port does not copy credentials. Codex itself may use its normal existing authentication.

Active probes remain separate and unvalidated by passive acceptance. The fixed upstream version forks sessions and submits real model turns through Codex app-server. Its nominal three answers are not a request cap: retries and a replacement question yield a conservative source-derived bound of 12 turn starts, or 18 with uncertain-result confirmation, excluding Codex internal retries and repeated scheduled runs. Forks can expose source-session history and consume account quota. Tool-denial prompts and approval refusal alone do not prove that all tool execution is impossible.

The original account marker reads `auth.json`, derives account metadata from JWT content, and may hash an API key. A truncated hash can still link records and is not anonymous. The Windows default exits before that read. Statistical fingerprint MATCH has stricter thresholds in this port but remains classification against a finite reference bank, not proof of a server model's identity, weights, or routing.

Approving passive installation does not authorize active forks, model requests, credential reads, broad session discovery, or updates. Do not use a different model, cloud conversation, or subagent as a substitute for the current local model.

## Reproducible passive validation

Use a reviewed checkout and native executables. The following examples contain no machine-specific username, session ID, or absolute installation path:

```powershell
$nerfedCodexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$nerfedCodexExe = Join-Path $nerfedCodexDir '.sandbox-bin\codex.exe'
$nerfedPythonExe = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
& $nerfedPythonExe -I -B -m unittest discover -s tests -p test_windows.py -v
.\install-windows.ps1 -CodexPath $nerfedCodexExe -PythonPath $nerfedPythonExe -CodexHome $nerfedCodexDir -WhatIf
```

Choose the actual reviewed native `codex.exe` explicitly if it is located elsewhere. Install only at the authorized target after the preview. Review and trust the exact passive hook definitions in the local `/hooks` interface after execution has been authorized. No remote shell script, administrator privileges, PATH change, persistent account authorization, or Windows sandbox bypass is required.

The Windows tests use temporary state roots, fixed synthetic UUIDs, mocked network/credential paths, and controlled Python and PowerShell subprocess fixtures. The 18 Windows regression tests include all five manifest commands through real outer Windows PowerShell and available pwsh, with clean stderr, scoped passive evidence, and no active probes. Two parity tests check the fingerprint calculations. They check passive event handling, credential-read guards, default network/process guards, rollout scope, locking, and process behavior without running Codex model turns. Run only these explicit test targets, rather than indiscriminately discovering other repository tests.

Report validation at the level actually observed:

| Evidence | What it establishes |
| --- | --- |
| Static review and offline tests | Checked code paths and synthetic expectations; not complete runtime or server behavior |
| Isolated install/uninstall/reinstall | Marketplace and plugin registration plus scoped rollback for that CLI version |
| Hook trust metadata | The current definitions were trusted; it does not prove an event was emitted |
| Synthetic invocation of installed hook commands | Those commands can process their fixtures through the installed runtime |
| A naturally emitted event from a dedicated local client | That particular client event reached the plugin; other lifecycle events remain unverified until observed |

Keep active, account, discovery, and update flags disabled throughout passive validation. An empty native client startup can exercise startup behavior without submitting a model prompt; it cannot demonstrate turn or stop events. Do not scan unrelated real sessions for acceptance. Private raw logs should remain local; publish only redacted conclusions, commands, versions, and synthetic fixtures. This document is a validation procedure, not a claim that every natural lifecycle event has been observed.

For rollback, preview the managed uninstaller at `<CodexHome>/is-gpt-nerfed/windows-marketplace/uninstall-windows.ps1`, then run it against the same authorized Codex home. Retained `config.toml` backups are for reviewed manual recovery; avoid overwriting unrelated later settings. Restart Codex after hook changes or removal.

## Public distribution checklist

Commit reviewed code, documentation, and synthetic tests with the original history and notices. Exclude `__pycache__`, `.pyc`, `windows-runtime.json`, installation journals, generated `config.json`, logs, session evidence, configuration backups, and local test output. Existing `.gitignore` rules cover bytecode, but inspect the actual Git index and proposed commit as well.

Documentation examples should use environment variables or placeholders. Do not publish real user/profile paths, account identifiers, credentials, session IDs, or private rollout contents. The synthetic all-ones/all-twos UUIDs in the offline tests are fixture identifiers, not actual sessions. Preserve the original ModelTrace data and provenance rather than replacing them with local measurement results.
