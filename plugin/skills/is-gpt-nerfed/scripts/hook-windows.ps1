# Windows hook adapter. Runtime paths are written by install-windows.ps1.
# Any adapter error must leave the user's Codex turn unblocked.
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('SessionStart','UserPromptSubmit','PreToolUse','Stop','SessionEnd')][string]$Event)
$ErrorActionPreference = 'Stop'
try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
    $runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not [System.IO.Path]::IsPathRooted($runtime.pythonPath) -or
        [System.IO.Path]::GetExtension($runtime.pythonPath) -ne '.exe' -or
        -not (Test-Path -LiteralPath $runtime.pythonPath -PathType Leaf)) { throw 'Python runtime is unavailable.' }
    $payload = [Console]::In.ReadToEnd()
    $env:CODEX_HOME = $runtime.codexHome
    $env:NERFED_HOME = $runtime.nerfedHome
    $result = ($payload | & $runtime.pythonPath -I -B (Join-Path $PSScriptRoot 'nerfed') hook --event $Event 2>$null) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or -not $result.Trim()) { Write-Output '{}' } else {
        $result | ConvertFrom-Json -ErrorAction Stop | Out-Null
        Write-Output $result
    }
} catch {
    Write-Output '{}'
}
exit 0
