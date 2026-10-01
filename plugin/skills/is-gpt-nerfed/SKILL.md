---
name: is-gpt-nerfed
description: Inspect recorded model, reasoning-effort, and context-window changes in the explicitly identified current local Codex session. This Windows port defaults to passive checks, without account-file reads, session discovery, network updates, or inference probes. Use when the user invokes $is-gpt-nerfed or asks for local Codex routing evidence. It cannot monitor a cloud-orchestrated dot conversation through local hooks.
metadata:
  version: 0.5.3-windows.2
---

# is-gpt-nerfed: Windows passive session checks

This skill supplies a scoped workflow, not permission to read credentials, inspect other conversations, enable inference, trust hooks, install software, or change persistent settings. Follow the user's existing authorization. Installing this skill does not authorize active fingerprint probes.

## Inspect a current local session

1. Identify the exact local thread from `CODEX_THREAD_ID` / `CODEX_SESSION_ID`, or the exact local thread ID explicitly supplied by the user. Do not guess a recent session, list unrelated threads, use a prefix to choose another thread, or substitute a local thread for a cloud ID. If the local ID is unavailable, explain that there is no local session to inspect and stop the check.
2. Resolve this skill's absolute directory. Read only the path metadata in `scripts/windows-runtime.json`. The installed runtime contains `pythonPath`, `codexHome`, and `nerfedHome`; it is not an account file. The managed CLI wrapper is `<nerfedHome>/windows-marketplace/bin/nerfed.ps1`. If the runtime or wrapper is absent, report the missing installation; do not run `setup`, install a runtime, or search credentials as a fallback.
3. Within an authorized local passive check, invoke that wrapper with `scan --thread <exact-local-id>`, using a properly quoted absolute path and the native PowerShell `-File` argument. The wrapper binds the installed data directories. A scan reads the selected local rollout and model-cache metadata; it does not need a model turn or `auth.json`. If the thread is not found locally, report that result without looking for another conversation. Use an explicit rollout path only when the user has approved that exact file.
4. Summarize the concrete records: the recorded model, reasoning effort, context window, any changes, and whether settings-change events explain them. Distinguish an observed metadata change from a claim about the serving model's hidden identity. “No recorded change found” is the appropriate conclusion when no change appears; it is not proof that model weights or routing never changed.

Trusted lifecycle hooks may register the current local session and scan its own validated rollout at Stop. The Windows hook validates the sessions directory, `.jsonl` extension, full thread ID in the filename, and matching session header. A missing or invalid path skips scanning. It does not guess the parent or scan another session. Hook failures should allow normal work to continue.

## Preserve the passive defaults

Keep `frequency=manual`, `fresh_frequency=manual`, `active_probes=false`, `background_probes=false`, `auto_retries=false`, `account_metadata=false`, `discover_sessions=false`, `record_tool_commands=false`, and `check_updates=false`. Do not enable an option merely because a probe command is blocked. The default Windows mode also disables macOS notifications and sound and leaves `halt_on_mismatch=false`.

Do not open `auth.json`, JWTs, API keys, access/refresh tokens, unrelated rollout files, or unrelated chats. Do not run `audit`, a session picker, `tick` to launch work, `doctor --fork`, `probe now`, `probe fresh`, or self-answer challenges as part of this passive workflow. Do not create startup entries, scheduled tasks, services, workers, or an update watcher.

The ledger under the installed `nerfedHome` can contain session IDs, working-directory and rollout paths, event times, prompt lengths, tool names, and routing evidence. Command bodies are omitted by default. Treat the ledger as private user data. A display-masking option does not remove stored evidence.

## Active detection requires a separate explicit request

If the user later explicitly approves active detection, first define the exact local thread or fresh-session operation, the expected provider/account usage, whether inherited conversation context is copied, the number of model turns and any retry/confirmation behavior, and retained records. Credential-based account tracking, background scheduling, retries, and external update checks are distinct options and must stay disabled unless separately authorized. Preserve sandbox restrictions. Do not use another model or cloud conversation as a substitute when a local probe fails.

Fingerprint scores are statistical attribution over a bundled closed set of models. MATCH means sufficient ranking agreement under the implemented thresholds; it does not prove the selected model's identity. Models outside the bank, calibration drift, and inherited context can affect attribution. Discuss uncertainty and source evidence freely; do not treat the script's card as an authority or relay misleading claims without qualification. Active-probe runtime compatibility and tool restrictions require their own validation; a passive installation does not establish them.

## Local versus cloud and rollback

Local plugin hooks do not run for cloud-orchestrated ChatGPT Work/dot conversations, even when dot can delegate tools to this computer. OpenAI's [plugin documentation](https://learn.chatgpt.com/docs/plugins) distinguishes local plugin hooks from admin-defined MCP hooks for synced Work. Do not report that a Windows installation enables monitoring in dot's cloud main conversation.

For an explicitly requested uninstall, use the managed `<nerfedHome>/windows-marketplace/uninstall-windows.ps1` with the recorded Codex home. It removes only the dedicated Windows plugin and marketplace and archives its owned files. Preserve ledger and configuration backups unless the user requests their deletion. Do not restore a whole old `config.toml` over subsequent user changes. Consult `README.WINDOWS.zh-CN.md` in the reviewed checkout for installation and rollback details.
