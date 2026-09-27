param(
    [Parameter(Mandatory=$true)][ValidateSet("open", "save", "save_as")][string]$Action,
    [Parameter(Mandatory=$true)][string]$Path,
    [string]$Content
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
. (Join-Path $repositoryRoot ".kinotch/scripts/path-containment.ps1")
$projectRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "project"))
if ([IO.Path]::IsPathRooted($Path)) {
    Write-Error "File path must be relative to the Project root"
    exit 1
}
$resolved = [IO.Path]::GetFullPath((Join-Path $projectRoot $Path))

if ($Action -eq "open") {
    $safeResolved = Assert-KntSafePath -Root $projectRoot -Candidate $resolved -Description "File path"
    if (-not (Test-Path -LiteralPath $safeResolved -PathType Leaf)) { Write-Error "File not found: $Path"; exit 1 }
    Get-Content -Raw -Encoding UTF8 -LiteralPath $safeResolved
    exit 0
}

$safeResolved = Assert-KntSafeWritePath -Root $projectRoot -Candidate $resolved -Description "File destination"
$parent = Split-Path -Parent $safeResolved
New-Item -ItemType Directory -Path $parent -Force | Out-Null
[IO.File]::WriteAllText($safeResolved, [string]$Content, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "File ${Action}: $Path"
exit 0
