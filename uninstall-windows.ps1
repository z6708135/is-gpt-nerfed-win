[CmdletBinding(SupportsShouldProcess)]
param([string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }))
$ErrorActionPreference = 'Stop'
$codexRoot = [System.IO.Path]::GetFullPath($CodexHome)
$stateRoot = Join-Path $codexRoot 'is-gpt-nerfed'
$statePath = Join-Path $stateRoot 'windows-install-state.json'
function Assert-NoReparseParent([string]$Path) {
    $cursor = [System.IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw "Refusing reparse-point path: $cursor" }
        }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
Assert-NoReparseParent $statePath
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { throw 'Managed Windows installation journal not found; no files changed.' }
$journal = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedRoot = Join-Path $stateRoot 'windows-marketplace'
if ($journal.owner -ne 'is-gpt-nerfed-windows-port' -or $journal.pluginId -ne 'is-gpt-nerfed@is-gpt-nerfed-windows' -or
    $journal.marketplace -ne 'is-gpt-nerfed-windows' -or
    [System.IO.Path]::GetFullPath($journal.marketRoot) -ne $expectedRoot -or
    [System.IO.Path]::GetFullPath($journal.codexHome) -ne $codexRoot) { throw 'Installation journal scope does not match; no files changed.' }
$cursor = $expectedRoot
while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw "Refusing reparse-point path: $cursor" }
    }
    $parent = Split-Path $cursor -Parent
    if ($parent -eq $cursor) { break }
    $cursor = $parent
}
$signature = Get-AuthenticodeSignature -LiteralPath $journal.codexPath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'OpenAI') { throw 'Recorded Codex executable no longer has a valid OpenAI signature.' }
if (-not $PSCmdlet.ShouldProcess($expectedRoot, 'Remove only the dedicated plugin and marketplace registration, and archive its installed files')) { return }
$priorCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $codexRoot
    $marketData = (& $journal.codexPath plugin marketplace list --json | Out-String) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the marketplace registry; files and journal were retained.' }
    $matchingMarkets = @($marketData.marketplaces | Where-Object { $_.name -eq $journal.marketplace })
    if ($matchingMarkets.Count -gt 1 -or ($matchingMarkets.Count -eq 1 -and [System.IO.Path]::GetFullPath($matchingMarkets[0].root) -ne $expectedRoot)) {
        throw 'Marketplace name now points elsewhere; refusing to modify it.'
    }
    $pluginData = (& $journal.codexPath plugin list --marketplace $journal.marketplace --json | Out-String) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the dedicated plugin state; files and journal were retained.' }
    $installed = @($pluginData.installed | Where-Object { $_.pluginId -eq $journal.pluginId -and $_.marketplaceName -eq $journal.marketplace })
    if ($installed.Count) {
        & $journal.codexPath plugin remove $journal.pluginId
        if ($LASTEXITCODE -ne 0) { throw 'Plugin removal failed; files and journal were retained. Inspect the exact entry in /plugins.' }
    }
    if ($matchingMarkets.Count) {
        & $journal.codexPath plugin marketplace remove $journal.marketplace
        if ($LASTEXITCODE -ne 0) { throw 'Marketplace removal failed; files and journal were retained. Inspect the exact marketplace entry.' }
    }
} finally {
    if ($null -eq $priorCodexHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue } else { $env:CODEX_HOME = $priorCodexHome }
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
$archivePath = Join-Path $stateRoot ('windows-marketplace.uninstalled-' + $stamp)
# Both absolute targets are verified as children of this installation's state root.
if ((Split-Path ([System.IO.Path]::GetFullPath($archivePath)) -Parent) -ne $stateRoot) { throw 'Invalid archive target.' }
if (Test-Path -LiteralPath $archivePath) { throw 'Archive target already exists; no files moved.' }
Assert-NoReparseParent $archivePath
# Archive only the unchanged passive configuration created by this installer.
$pluginConfig = Join-Path $stateRoot 'config.json'
Assert-NoReparseParent $pluginConfig
$configArchive = Join-Path $stateRoot ('config.uninstalled-' + $stamp + '.json')
$journalArchive = Join-Path $stateRoot ('windows-install-state.uninstalled-' + $stamp + '.json')
foreach ($target in @($configArchive, $journalArchive)) {
    Assert-NoReparseParent $target
    if (Test-Path -LiteralPath $target) { throw 'Archive target already exists; no files moved.' }
}
if ((Test-Path -LiteralPath $pluginConfig -PathType Leaf) -and $journal.pluginConfigSha256 -and
    (Get-FileHash -LiteralPath $pluginConfig).Hash -eq $journal.pluginConfigSha256) {
    Move-Item -LiteralPath $pluginConfig -Destination $configArchive
}
if (Test-Path -LiteralPath $expectedRoot) { Move-Item -LiteralPath $expectedRoot -Destination $archivePath }
Move-Item -LiteralPath $statePath -Destination $journalArchive
Write-Output "Unregistered the dedicated Windows plugin. Restart local Codex to unload hooks. Files archived at $archivePath."
Write-Output 'Ledger, passive configuration, configuration backups, and other plugin settings remain available. No data was purged.'
