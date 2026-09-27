param(
    [Alias('Root')][string]$BaseRoot
)

$PathContainmentPath = Join-Path $PSScriptRoot "path-containment.ps1"
if (Test-Path -LiteralPath $PathContainmentPath -PathType Leaf) {
    . $PathContainmentPath
}

function ConvertTo-BaseRelativePath {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$AbsolutePath
    )

    $rootValue = ([string]$Root).Replace('\', '/')
    $pathValue = ([string]$AbsolutePath).Replace('\', '/')
    while ($rootValue.Length -gt 1 -and $rootValue.EndsWith('/')) {
        $rootValue = $rootValue.Substring(0, $rootValue.Length - 1)
    }

    if ($rootValue -eq '/') {
        return $pathValue.TrimStart('/')
    }
    if ($pathValue -eq $rootValue) {
        return ''
    }

    $prefix = $rootValue + '/'
    $windowsPath = ($env:OS -eq "Windows_NT") -or ($rootValue -match '^[A-Za-z]:/')
    $comparison = if ($windowsPath) { [System.StringComparison]::OrdinalIgnoreCase } else { [System.StringComparison]::Ordinal }
    if (-not $pathValue.StartsWith($prefix, $comparison)) {
        throw "Path is outside repository root: $AbsolutePath"
    }
    return $pathValue.Substring($prefix.Length).TrimStart('/')
}

function Get-BaseFileHash {
    param([Parameter(Mandatory=$true)][string]$Path)

    $content = [IO.File]::ReadAllText($Path)
    return (Get-BaseTextHash -Text $content)
}

function Get-BaseTextHash {
    param([Parameter(Mandatory=$true)][string]$Text)

    $content = [string]$Text
    $canonical = $content.Replace("`r`n", "`n").Replace("`r", "`n")
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($canonical)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha256.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-BaseProtectedPaths {
    param([Parameter(Mandatory=$true)][string]$Root)

    $kinotchRoot = Join-Path $Root ".kinotch"
    if (-not (Test-Path -LiteralPath $kinotchRoot -PathType Container)) {
        throw "Base directory not found: $kinotchRoot"
    }
    $kinotchItem = Get-Item -LiteralPath $kinotchRoot -Force -ErrorAction Stop
    if (($kinotchItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Base directory crosses a symlink, junction, or reparse-point boundary: $kinotchRoot"
    }
    if (Get-Command Assert-KntSafePath -ErrorAction SilentlyContinue) {
        [void](Assert-KntSafePath -Root $Root -Candidate $kinotchRoot -Description "Base directory" -AllowRoot)
    }

    $fixed = @(
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".github/workflows/verify.yml",
        "AGENTS.md",
        "knt.cmd"
    )
    $common = @(Get-ChildItem -LiteralPath $kinotchRoot -Recurse -File -Force | ForEach-Object {
        if (Get-Command Assert-KntSafePath -ErrorAction SilentlyContinue) {
            [void](Assert-KntSafePath -Root $Root -Candidate $_.FullName -Description "Base protected file")
        }
        $relative = ConvertTo-BaseRelativePath -Root $Root -AbsolutePath $_.FullName
        if ($relative -ne ".kinotch/base-files.json") { $relative }
    })

    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($path in @($fixed + $common)) {
        if (-not $paths.Contains($path)) { [void]$paths.Add($path) }
    }
    $paths.Sort([System.StringComparer]::Ordinal)
    return $paths.ToArray()
}

function Normalize-BaseText([string]$Text) {
    return ([string]$Text).Replace("`r`n", "`n").Replace("`r", "`n")
}

function Assert-BaseIndexVersionIdentity {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string[]]$ProtectedPaths,
        [Parameter(Mandatory=$true)]$Entries,
        [Parameter(Mandatory=$true)][string]$Version
    )

    $indexPath = Join-Path $Root ".kinotch/base-files.json"
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { return }
    $existing = Get-Content -Raw -Encoding UTF8 -LiteralPath $indexPath | ConvertFrom-Json
    if ([string]$existing.base_version -ne $Version) { return }

    $existingEntries = @($existing.files | ForEach-Object {
        [pscustomobject]@{ path = [string]$_.path; sha256 = [string]$_.sha256 }
    } | Sort-Object path)
    $currentEntries = @($Entries | ForEach-Object {
        [pscustomobject]@{ path = [string]$_.path; sha256 = [string]$_.sha256 }
    } | Sort-Object path)
    $existingSnapshot = ConvertTo-Json $existingEntries -Compress -Depth 5
    $currentSnapshot = ConvertTo-Json $currentEntries -Compress -Depth 5
    $inventoryPath = Join-Path $Root ".kinotch/FILE_INVENTORY.txt"
    $expectedInventory = (($ProtectedPaths | Sort-Object) -join "`n") + "`n"
    $inventoryChanged = -not (Test-Path -LiteralPath $inventoryPath -PathType Leaf) -or
        (Normalize-BaseText (Get-Content -Raw -Encoding UTF8 -LiteralPath $inventoryPath)) -ne (Normalize-BaseText $expectedInventory)
    if ($existingSnapshot -ne $currentSnapshot -or $inventoryChanged) {
        throw "protected Base content changed without BASE_VERSION bump"
    }
}

function Update-BaseIndex {
    param([Parameter(Mandatory=$true)][string]$Root)

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $manifestPath = Join-Path $resolvedRoot "project/project.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "project/project.json not found: $manifestPath"
    }
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
    if ($manifest.project.type -ne "repository-base") {
        throw "base-refresh is only available for project.type repository-base"
    }

    $protectedPaths = @(Get-BaseProtectedPaths -Root $resolvedRoot)
    $version = (Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $resolvedRoot ".kinotch/BASE_VERSION")).Trim()
    $inventoryContent = (($protectedPaths | Sort-Object) -join "`n") + "`n"
    $entries = New-Object System.Collections.Generic.List[object]
    foreach ($relative in $protectedPaths) {
        $path = Join-Path $resolvedRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Base protected file not found: $relative"
        }
        if (Get-Command Assert-KntSafePath -ErrorAction SilentlyContinue) {
            [void](Assert-KntSafePath -Root $resolvedRoot -Candidate $path -Description "Base protected file")
        }
        $hash = if ($relative -eq ".kinotch/FILE_INVENTORY.txt") {
            Get-BaseTextHash -Text $inventoryContent
        }
        else {
            Get-BaseFileHash -Path $path
        }
        [void]$entries.Add([pscustomobject]@{
            path = $relative
            sha256 = $hash
        })
    }
    Assert-BaseIndexVersionIdentity -Root $resolvedRoot -ProtectedPaths $protectedPaths -Entries $entries.ToArray() -Version $version
    $index = [pscustomobject]@{
        schema_version = 1
        base_version = $version
        files = $entries.ToArray()
    }
    $json = ConvertTo-Json $index -Depth 10
    $inventoryPath = Join-Path $resolvedRoot ".kinotch/FILE_INVENTORY.txt"
    $indexPath = Join-Path $resolvedRoot ".kinotch/base-files.json"
    if (Get-Command Assert-KntSafeWritePath -ErrorAction SilentlyContinue) {
        [void](Assert-KntSafeWritePath -Root $resolvedRoot -Candidate $inventoryPath -Description "Base inventory write")
        [void](Assert-KntSafeWritePath -Root $resolvedRoot -Candidate $indexPath -Description "Base index write")
    }
    [IO.File]::WriteAllText($inventoryPath, $inventoryContent, (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($indexPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

if (-not [string]::IsNullOrWhiteSpace($BaseRoot)) {
    Update-BaseIndex -Root $BaseRoot
}
