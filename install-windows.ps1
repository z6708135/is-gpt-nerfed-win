# Run only after the reviewed Windows port and this installation have been approved.
# Source release 0.5.3-windows.2 uses encoded hook dispatch; existing installations are not updated by source edits.
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$CodexPath,
    [string]$PythonPath,
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' })
)
$ErrorActionPreference = 'Stop'
$marketName = 'is-gpt-nerfed-windows'
$pluginId = 'is-gpt-nerfed@is-gpt-nerfed-windows'
$codexRoot = [System.IO.Path]::GetFullPath($CodexHome)
$stateRoot = Join-Path $codexRoot 'is-gpt-nerfed'
$marketRoot = Join-Path $stateRoot 'windows-marketplace'
$statePath = Join-Path $stateRoot 'windows-install-state.json'
function Write-JsonUtf8([string]$Path, $Value) {
    [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))
}
function Assert-NoReparseParent([string]$Path) {
    $cursor = [System.IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Refusing reparse-point path: $cursor"
            }
        }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
Assert-NoReparseParent $stateRoot
Assert-NoReparseParent (Join-Path $codexRoot 'config.toml')
Assert-NoReparseParent (Join-Path $stateRoot 'windows-backups')
if (-not $CodexPath) { $CodexPath = Join-Path $codexRoot '.sandbox-bin\codex.exe' }
if (-not $PythonPath) { $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source }
$CodexPath = (Resolve-Path -LiteralPath $CodexPath).Path
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
foreach ($exe in @($CodexPath,$PythonPath)) {
    if ([System.IO.Path]::GetExtension($exe) -ne '.exe' -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'Supply native executable paths; .cmd/.bat wrappers are not accepted.'
    }
}
$signature = Get-AuthenticodeSignature -LiteralPath $CodexPath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'OpenAI') {
    throw 'The Codex executable must have a valid OpenAI Authenticode signature.'
}
if (Test-Path -LiteralPath $marketRoot) { throw "Installation already exists: $marketRoot. Use the reviewed uninstaller before reinstalling." }
if (Test-Path -LiteralPath $statePath) { throw 'Installation journal already exists; review or uninstall the previous attempt first.' }
if (Test-Path -LiteralPath (Join-Path $stateRoot 'config.json')) { throw 'Existing plugin configuration found; review migration without overwriting it.' }
$pluginSource = Join-Path $PSScriptRoot 'plugin'
if (-not (Test-Path -LiteralPath (Join-Path $pluginSource '.codex-plugin\plugin.json'))) { throw 'Plugin source is incomplete.' }
Assert-NoReparseParent $pluginSource
if (@(Get-ChildItem -LiteralPath $pluginSource -Recurse -Force | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Plugin source contains reparse points; review before copying.'
}
if (-not $PSCmdlet.ShouldProcess($marketRoot, 'Copy the reviewed port and register its dedicated Codex marketplace and plugin; keep hooks untrusted')) { return }
# Check for an existing source with the same name before any installation writes.
$priorCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $codexRoot
    $marketData = (& $CodexPath plugin marketplace list --json | Out-String) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the existing marketplace registry safely.' }
    if (@($marketData.marketplaces | Where-Object { $_.name -eq $marketName }).Count) { throw 'The dedicated marketplace name is already registered; review it before installing.' }
    $pluginData = (& $CodexPath plugin list --marketplace $marketName --json | Out-String) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the dedicated plugin state safely.' }
    if (@($pluginData.installed | Where-Object { $_.pluginId -eq $pluginId }).Count) { throw 'The dedicated plugin is already installed; review it before installing.' }
} finally {
    if ($null -eq $priorCodexHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue } else { $env:CODEX_HOME = $priorCodexHome }
}
New-Item -ItemType Directory -Path $marketRoot -Force | Out-Null
$journal = [ordered]@{ schema=1; owner='is-gpt-nerfed-windows-port'; marketplace=$marketName; pluginId=$pluginId; codexPath=$CodexPath; codexHome=$codexRoot; marketRoot=$marketRoot; phase='copying'; created=[DateTime]::UtcNow.ToString('o') }
function Save-Journal { Write-JsonUtf8 $statePath $journal }
Save-Journal
Copy-Item -LiteralPath $pluginSource -Destination (Join-Path $marketRoot 'plugin') -Recurse
$scriptDir = Join-Path $marketRoot 'plugin\skills\is-gpt-nerfed\scripts'
Write-JsonUtf8 (Join-Path $scriptDir 'windows-runtime.json') @{ pythonPath=$PythonPath; codexHome=$codexRoot; nerfedHome=$stateRoot }
New-Item -ItemType Directory -Path (Join-Path $marketRoot 'bin'),(Join-Path $marketRoot '.agents\plugins') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'bin\nerfed.ps1') -Destination (Join-Path $marketRoot 'bin\nerfed.ps1')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall-windows.ps1') -Destination (Join-Path $marketRoot 'uninstall-windows.ps1')
Write-JsonUtf8 (Join-Path $marketRoot '.agents\plugins\marketplace.json') @{ name=$marketName; interface=@{displayName='Is GPT nerfed? (Windows, passive by default)'}; plugins=@(@{name='is-gpt-nerfed'; source=@{source='local'; path='./plugin'}; policy=@{installation='AVAILABLE'; authentication='ON_INSTALL'}; category='Developer Tools'}) }
Write-JsonUtf8 (Join-Path $stateRoot 'config.json') @{ frequency='manual'; mode='nudge'; fresh_frequency='manual'; active_probes=$false; background_probes=$false; auto_retries=$false; account_metadata=$false; discover_sessions=$false; record_tool_commands=$false; check_updates=$false; notify=$false; sound=$false; halt_on_mismatch=$false; passive=$true; hide_titles=$true; codex_bin=$CodexPath }
$journal.pluginConfigSha256 = (Get-FileHash -LiteralPath (Join-Path $stateRoot 'config.json')).Hash
Save-Journal
# Preserve the pre-install configuration as opaque bytes; never inspect auth.json.
$configPath = Join-Path $codexRoot 'config.toml'
if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $backupDir = Join-Path $stateRoot 'windows-backups'
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $backupPath = Join-Path $backupDir ('config-before-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '.toml')
    Copy-Item -LiteralPath $configPath -Destination $backupPath
    $journal.configBackup = $backupPath
    $journal.configBeforeSha256 = (Get-FileHash -LiteralPath $configPath).Hash
}
$journal.phase = 'registering-marketplace'; Save-Journal
$priorCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $codexRoot
    & $CodexPath plugin marketplace add $marketRoot
    if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed; the journal and files are retained for rollback.' }
    $journal.marketplaceAdded = $true
    $journal.phase = 'installing-plugin'; Save-Journal
    & $CodexPath plugin add $pluginId
    if ($LASTEXITCODE -ne 0) { throw 'Plugin registration failed; the journal and files are retained for rollback.' }
    $journal.pluginAdded = $true
} finally {
    if ($null -eq $priorCodexHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue } else { $env:CODEX_HOME = $priorCodexHome }
}
$journal.phase = 'registered-untrusted'
if (Test-Path -LiteralPath $configPath -PathType Leaf) { $journal.configAfterSha256 = (Get-FileHash -LiteralPath $configPath).Hash }
Save-Journal
Write-Output "Registered $pluginId. Review and trust its hooks separately in Codex /hooks after approval."
Write-Output 'No probe, daemon, scheduled task, PATH change, hook trust, or credential access was requested by this installer.'
Write-Output "CLI wrapper: $(Join-Path $marketRoot 'bin\nerfed.ps1')"
Write-Output "Rollback: $(Join-Path $marketRoot 'uninstall-windows.ps1')"
