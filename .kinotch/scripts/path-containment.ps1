function ConvertTo-KntCanonicalPath {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][bool]$Windows
    )

    if ($Windows -and $Path -match '^[A-Za-z]:[\\/]') {
        $normalized = ($Path -replace '/', '\')
        $drive = $normalized.Substring(0, 2)
        $segments = $normalized.Substring(2).Split('\', [System.StringSplitOptions]::RemoveEmptyEntries)
        $stack = New-Object System.Collections.Generic.List[string]
        foreach ($segment in $segments) {
            if ($segment -eq '.') { continue }
            if ($segment -eq '..') {
                if ($stack.Count -gt 0) { [void]$stack.RemoveAt($stack.Count - 1) }
                continue
            }
            [void]$stack.Add($segment)
        }
        if ($stack.Count -eq 0) { return "$drive\" }
        return "$drive\" + ($stack -join '\')
    }

    $normalizedPath = if ($Windows) { $Path.Replace('/', '\') } else { $Path.Replace('\', '/') }
    if (-not $Windows -and $normalizedPath.StartsWith('/')) {
        $segments = $normalizedPath.Split('/', [System.StringSplitOptions]::RemoveEmptyEntries)
        $stack = New-Object System.Collections.Generic.List[string]
        foreach ($segment in $segments) {
            if ($segment -eq '.') { continue }
            if ($segment -eq '..') {
                if ($stack.Count -gt 0) { [void]$stack.RemoveAt($stack.Count - 1) }
                continue
            }
            [void]$stack.Add($segment)
        }
        if ($stack.Count -eq 0) { return '/' }
        return '/' + ($stack -join '/')
    }
    return [IO.Path]::GetFullPath($normalizedPath)
}

function Get-KntPathComparison {
    param([Parameter(Mandatory=$true)][bool]$Windows)
    if ($Windows) { return [System.StringComparison]::OrdinalIgnoreCase }
    return [System.StringComparison]::Ordinal
}

function Test-KntProjectPathContained {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Candidate,
        [bool]$Windows = ($env:OS -eq "Windows_NT"),
        [switch]$AllowRoot
    )

    $rootPath = ConvertTo-KntCanonicalPath -Path $Root -Windows $Windows
    $candidatePath = ConvertTo-KntCanonicalPath -Path $Candidate -Windows $Windows
    $comparison = Get-KntPathComparison -Windows $Windows
    $separator = if ($Windows) { '\' } else { '/' }
    $trimmedRoot = $rootPath
    if ($trimmedRoot.Length -gt 1 -and -not ($Windows -and $trimmedRoot -match '^[A-Za-z]:\\$')) {
        $trimmedRoot = $trimmedRoot.TrimEnd([char[]]@('/', '\'))
    }
    if ([string]::Equals($trimmedRoot, $candidatePath, $comparison)) { return [bool]$AllowRoot }
    $prefix = if ($trimmedRoot.EndsWith($separator, $comparison)) { $trimmedRoot } else { $trimmedRoot + $separator }
    return $candidatePath.StartsWith($prefix, $comparison)
}

function Test-KntPathHasReparseBoundary {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Candidate,
        [bool]$Windows = ($env:OS -eq "Windows_NT")
    )

    $rootPath = ConvertTo-KntCanonicalPath -Path $Root -Windows $Windows
    $candidatePath = ConvertTo-KntCanonicalPath -Path $Candidate -Windows $Windows
    $comparison = Get-KntPathComparison -Windows $Windows
    if ([string]::Equals($rootPath, $candidatePath, $comparison)) { return $false }

    $current = $candidatePath
    while (-not [string]::Equals($current, $rootPath, $comparison)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                return $true
            }
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or [string]::Equals($parent, $current, $comparison)) {
            break
        }
        $current = ConvertTo-KntCanonicalPath -Path $parent -Windows $Windows
    }
    return $false
}

function Assert-KntSafePath {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Candidate,
        [Parameter(Mandatory=$true)][string]$Description,
        [bool]$Windows = ($env:OS -eq "Windows_NT"),
        [switch]$AllowRoot
    )

    $rootPath = ConvertTo-KntCanonicalPath -Path $Root -Windows $Windows
    $candidatePath = ConvertTo-KntCanonicalPath -Path $Candidate -Windows $Windows
    if (-not (Test-KntProjectPathContained -Root $rootPath -Candidate $candidatePath -Windows $Windows -AllowRoot:$AllowRoot)) {
        throw "$Description escapes its root boundary: $Candidate"
    }
    if (Test-KntPathHasReparseBoundary -Root $rootPath -Candidate $candidatePath -Windows $Windows) {
        throw "$Description crosses a symlink, junction, or reparse-point boundary: $Candidate"
    }
    return $candidatePath
}

function Assert-KntSafeWritePath {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Candidate,
        [Parameter(Mandatory=$true)][string]$Description,
        [bool]$Windows = ($env:OS -eq "Windows_NT"),
        [switch]$AllowRoot
    )

    return Assert-KntSafePath -Root $Root -Candidate $Candidate -Description $Description -Windows $Windows -AllowRoot:$AllowRoot
}
