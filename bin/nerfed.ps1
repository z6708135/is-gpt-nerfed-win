[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments)][string[]]$NerfedArgs)
$ErrorActionPreference = 'Stop'
$scripts = Join-Path (Split-Path $PSScriptRoot -Parent) 'plugin\skills\is-gpt-nerfed\scripts'
$runtimePath = Join-Path $scripts 'windows-runtime.json'
if (-not (Test-Path -LiteralPath $runtimePath -PathType Leaf)) {
    throw 'Use install-windows.ps1 after review and approval, or invoke the Python script directly with an explicit Python path.'
}
$runtime = Get-Content -LiteralPath $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not [System.IO.Path]::IsPathRooted($runtime.pythonPath) -or
    [System.IO.Path]::GetExtension($runtime.pythonPath) -ne '.exe' -or
    -not (Test-Path -LiteralPath $runtime.pythonPath -PathType Leaf)) { throw 'Python runtime is unavailable.' }
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$priorCodexHome = $env:CODEX_HOME
$priorNerfedHome = $env:NERFED_HOME
try {
    $env:CODEX_HOME = $runtime.codexHome
    $env:NERFED_HOME = $runtime.nerfedHome
    & $runtime.pythonPath -I -B (Join-Path $scripts 'nerfed') @NerfedArgs
    $status = $LASTEXITCODE
} finally {
    if ($null -eq $priorCodexHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue } else { $env:CODEX_HOME = $priorCodexHome }
    if ($null -eq $priorNerfedHome) { Remove-Item Env:NERFED_HOME -ErrorAction SilentlyContinue } else { $env:NERFED_HOME = $priorNerfedHome }
}
exit $status
