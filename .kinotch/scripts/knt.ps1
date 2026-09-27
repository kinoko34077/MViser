param(
    [string]$RootOverride,
    [string]$BaseOverride,

    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

if ($RootOverride) {
    $Root = (Resolve-Path -LiteralPath $RootOverride).Path
    if ($BaseOverride) {
        $BaseDir = (Resolve-Path -LiteralPath $BaseOverride).Path
    }
    else {
        $BaseDir = Join-Path $Root ".kinotch"
    }
}
else {
    $BaseDir = Split-Path -Parent $PSScriptRoot
    $Root = Split-Path -Parent $BaseDir
}

$ManifestPath = Join-Path $Root "project/project.json"
$BaseFilesPath = Join-Path $BaseDir "base-files.json"
$ValidationPath = Join-Path $BaseDir "scripts/knt-validation.ps1"
$BaseIndexScriptPath = Join-Path $BaseDir "scripts/update-base-index.ps1"

if (-not (Test-Path -LiteralPath $ValidationPath -PathType Leaf)) {
    throw "Validation script not found: $ValidationPath"
}
. $ValidationPath
if (-not (Test-Path -LiteralPath $BaseIndexScriptPath -PathType Leaf)) {
    throw "Base index script not found: $BaseIndexScriptPath"
}
. $BaseIndexScriptPath
$PathContainmentPath = Join-Path $BaseDir "scripts/path-containment.ps1"
if (-not (Test-Path -LiteralPath $PathContainmentPath -PathType Leaf)) {
    throw "Path containment helper not found: $PathContainmentPath"
}
. $PathContainmentPath

function Write-Knt([string]$Message) {
    Write-Host "[knt] $Message"
}

function Assert-RepositoryWriteAllowed([string]$Operation) {
    if (-not [string]::IsNullOrWhiteSpace($BaseOverride)) {
        throw "$Operation requires repository-local .kinotch; -BaseOverride is read-only"
    }

    $localBaseDir = Join-Path $Root ".kinotch"
    if (-not (Test-Path -LiteralPath $localBaseDir -PathType Container)) {
        throw "$Operation requires a valid repository-local .kinotch/ Base"
    }
    $localBaseItem = Get-Item -LiteralPath $localBaseDir -Force -ErrorAction Stop
    if (($localBaseItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Operation rejects a symlink, junction, or reparse-point repository-local .kinotch/ Base"
    }
    [void](Assert-KntSafePath -Root $Root -Candidate $localBaseDir -Description "repository-local Base" -AllowRoot)
    foreach ($requiredFile in @("BASE_VERSION", "base-files.json", "scripts/knt.ps1")) {
        if (-not (Test-Path -LiteralPath (Join-Path $localBaseDir $requiredFile) -PathType Leaf)) {
            throw "$Operation requires a valid repository-local .kinotch/ Base"
        }
    }

    $localResolved = (Resolve-Path -LiteralPath $localBaseDir).Path
    $activeResolved = (Resolve-Path -LiteralPath $BaseDir).Path
    $pathComparison = Get-KntPathComparison -Windows ($env:OS -eq "Windows_NT")
    if (-not [string]::Equals($localResolved, $activeResolved, $pathComparison)) {
        throw "$Operation requires the repository-local .kinotch/ Base"
    }
}

function Get-Manifest {
    return Get-KntJson -Path $ManifestPath
}

function Resolve-KntContainedPath {
    param(
        [Parameter(Mandatory=$true)][string]$BaseRoot,
        [Parameter(Mandatory=$true)][string]$RelativePath,
        [Parameter(Mandatory=$true)][string]$Description,
        [switch]$AllowRoot
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw "$Description must not be empty"
    }
    $candidateText = [string]$RelativePath
    if ([IO.Path]::IsPathRooted($candidateText) -or $candidateText -match '^(?:[A-Za-z]:)?[\\/]') {
        throw "$Description must be a relative path inside the repository boundary: $RelativePath"
    }
    $basePath = [IO.Path]::GetFullPath($BaseRoot)
    $candidatePath = [IO.Path]::GetFullPath((Join-Path $basePath $candidateText))
    $contained = if ($AllowRoot) {
        Test-KntProjectPathContained -Root $basePath -Candidate $candidatePath -AllowRoot
    }
    else {
        Test-KntProjectPathContained -Root $basePath -Candidate $candidatePath
    }
    if (-not $contained) {
        throw "$Description escapes its root boundary: $RelativePath"
    }
    return Assert-KntSafePath -Root $basePath -Candidate $candidatePath -Description $Description -AllowRoot:$AllowRoot
}

function Resolve-KntManifestProjectPath {
    param(
        [Parameter(Mandatory=$true)]$Manifest,
        [Parameter(Mandatory=$true)][string]$Name,
        [string]$Default = "."
    )
    $relative = Get-ManifestPathValue -Manifest $Manifest -Name $Name -Default $Default
    return Resolve-KntContainedPath -BaseRoot (Join-Path $Root "project") -RelativePath $relative -Description "Manifest path '$Name'" -AllowRoot
}

function Resolve-KntCommandWorkingDirectory {
    param(
        [Parameter(Mandatory=$true)][string]$RelativePath,
        [string]$CommandName = "command"
    )
    return Resolve-KntContainedPath -BaseRoot $Root -RelativePath $RelativePath -Description "Command '$CommandName' cwd" -AllowRoot
}

function Test-DefaultCatalogSemantics($Catalog) {
    $errors = New-Object System.Collections.Generic.List[string]
    $ids = @{}
    $aliases = @{}
    foreach ($entry in @($Catalog.defaults)) {
        $id = [string]$entry.id
        if ($ids.ContainsKey($id)) {
            [void]$errors.Add("duplicate Default id '$id'")
        }
        else {
            $ids[$id] = $true
        }
        foreach ($aliasValue in @($entry.aliases)) {
            $alias = [string]$aliasValue
            if ($aliases.ContainsKey($alias)) {
                [void]$errors.Add("duplicate Default alias '$alias'")
            }
            else {
                $aliases[$alias] = $true
            }
        }
        if ([string]$entry.kind -eq "surface") {
            $profileName = Get-DefaultProfileName $entry
            $profilePath = Join-Path $BaseDir ("profiles/" + $profileName + ".json")
            if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
                [void]$errors.Add("Surface Default '$id' references missing profile '$profileName'")
            }
        }
    }
    foreach ($id in @($ids.Keys)) {
        if ($aliases.ContainsKey([string]$id)) {
            [void]$errors.Add("Default id/alias collision '$id'")
        }
    }
    $currentOwners = @{}
    foreach ($entry in @($Catalog.defaults)) {
        $entryId = [string]$entry.id
        foreach ($path in @(Get-DefaultTemplateRepositoryPaths -DefaultId $entryId)) {
            $key = Get-KntRepositoryPathKey $path
            if ($currentOwners.ContainsKey($key) -and $currentOwners[$key] -ne $entryId) {
                [void]$errors.Add("Default template path '$path' is owned by both '$($currentOwners[$key])' and '$entryId'")
            }
            else {
                $currentOwners[$key] = $entryId
            }
        }
    }
    foreach ($entry in @($Catalog.defaults)) {
        $entryId = [string]$entry.id
        $current = @{}
        foreach ($path in @(Get-DefaultTemplateRepositoryPaths -DefaultId $entryId)) { $current[(Get-KntRepositoryPathKey $path)] = $true }
        $retired = @{}
        $retiredPaths = if ($entry.PSObject.Properties["retired_paths"]) { @($entry.retired_paths) } else { @() }
        foreach ($retiredPath in $retiredPaths) {
            $path = ConvertTo-KntRepositoryRelativePath ([string]$retiredPath)
            $key = Get-KntRepositoryPathKey $path
            if (-not (Test-KntRepositoryRelativePathSyntax $path)) {
                [void]$errors.Add("Default '$entryId' retired path '$retiredPath' is not a repository-relative path")
            }
            if ($retired.ContainsKey($key)) {
                [void]$errors.Add("Default '$entryId' retired path '$path' is duplicated")
            }
            else { $retired[$key] = $true }
            if ($current.ContainsKey($key)) {
                [void]$errors.Add("Default '$entryId' retired path '$path' is still a current template path")
            }
            if ($currentOwners.ContainsKey($key) -and $currentOwners[$key] -ne $entryId) {
                [void]$errors.Add("Default '$entryId' retired path '$path' overlaps current Default '$($currentOwners[$key])'")
            }
        }
    }
    return @($errors | Select-Object -Unique)
}

function Get-ProjectDefaultState($Manifest, [string]$DefaultId) {
    if (-not $Manifest) { return $null }
    try {
        $path = Resolve-KntManifestProjectPath -Manifest $Manifest -Name "defaults" -Default "defaults.json"
    }
    catch {
        return $null
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    $defaults = Get-KntJson -Path $path
    $property = $defaults.packs.PSObject.Properties[$DefaultId]
    if (-not $property) {
        $catalog = Get-DefaultCatalog
        $entry = Find-AnyDefaultCatalogEntry -Catalog $catalog -Identifier $DefaultId
        $property = $defaults.packs.PSObject.Properties[[string]$entry.id]
    }
    if ($property) { return [string](Get-KntJsonProperty $property.Value "state") }
    return $null
}

function Test-ProjectDefaultEnabled($Manifest, [string]$DefaultId) {
    return ((Get-ProjectDefaultState -Manifest $Manifest -DefaultId $DefaultId) -eq "DEFAULT")
}

function Get-DefaultCatalog {
    $catalogPath = Join-Path $BaseDir "defaults/catalog.json"
    $schemaPath = Join-Path $BaseDir "schemas/default-catalog.schema.json"
    if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
        throw "Default catalog not found: $catalogPath"
    }
    if (-not (Test-Path -LiteralPath $schemaPath -PathType Leaf)) {
        throw "Default catalog schema not found: $schemaPath"
    }
    $catalog = Get-KntJson -Path $catalogPath
    $schema = Get-KntJson -Path $schemaPath
    $errors = @(Test-KntSchema -Data $catalog -Schema $schema -Path ".kinotch/defaults/catalog.json")
    if ($errors.Count -gt 0) {
        throw "Default catalog validation failed: " + ($errors -join "; ")
    }
    $semanticErrors = @(Test-DefaultCatalogSemantics -Catalog $catalog)
    if ($semanticErrors.Count -gt 0) {
        throw "Default catalog semantic validation failed: " + ($semanticErrors -join "; ")
    }
    return $catalog
}

function Get-DefaultCompatibilityError($Entry, [string[]]$SelectedSurfaces) {
    $compatible = @($Entry.compatible_surfaces)
    if ([string]$Entry.kind -ne "tool" -or $compatible.Count -eq 0) { return $null }
    $overlap = @($SelectedSurfaces | Where-Object { $_ -in $compatible })
    if ($overlap.Count -eq 0) {
        return "Default '$($Entry.id)' is not compatible with the selected Surface profile(s)"
    }
    return $null
}

function Get-DefaultCompatibilityKeys {
    param(
        $Catalog,
        [string[]]$ProfileIds = @(),
        [string[]]$SurfaceIds = @(),
        $ProfileEntries = @()
    )

    $keys = New-Object System.Collections.Generic.List[string]
    foreach ($profileId in @($ProfileIds)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$profileId) -and [string]$profileId -notin $keys) {
            [void]$keys.Add([string]$profileId)
        }
    }
    foreach ($entry in @($ProfileEntries)) {
        if ([string]$entry.kind -ne "surface") { continue }
        foreach ($value in @([string]$entry.id) + @($entry.compatible_surfaces)) {
            if (-not [string]::IsNullOrWhiteSpace([string]$value) -and [string]$value -notin $keys) {
                [void]$keys.Add([string]$value)
            }
        }
    }
    foreach ($surfaceId in @($SurfaceIds)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$surfaceId) -and [string]$surfaceId -notin $keys) {
            [void]$keys.Add([string]$surfaceId)
        }
        try {
            $entry = Find-DefaultCatalogEntry -Catalog $Catalog -Identifier ([string]$surfaceId) -Kind "surface"
            foreach ($value in @([string]$entry.id) + @($entry.compatible_surfaces)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$value) -and [string]$value -notin $keys) {
                    [void]$keys.Add([string]$value)
                }
            }
        }
        catch {
            # Existing custom Surface IDs remain visible as raw compatibility keys.
        }
    }
    return @($keys.ToArray())
}

function Find-DefaultCatalogEntry($Catalog, [string]$Identifier, [string]$Kind) {
    $matches = @($Catalog.defaults | Where-Object {
        ([string]$_.id -eq $Identifier) -or (@($_.aliases) -contains $Identifier)
    })
    if ($matches.Count -eq 0) {
        throw "Unknown $Kind Default '$Identifier' in Default catalog"
    }
    $entry = $matches[0]
    if ([string]$entry.kind -ne $Kind) {
        throw "Default '$Identifier' is kind '$($entry.kind)' and cannot be used as a $Kind Default"
    }
    return $entry
}

function Find-AnyDefaultCatalogEntry($Catalog, [string]$Identifier) {
    $matches = @($Catalog.defaults | Where-Object {
        ([string]$_.id -eq $Identifier) -or (@($_.aliases) -contains $Identifier)
    })
    if ($matches.Count -eq 0) {
        throw "Unknown Default Pack '$Identifier' in Default catalog"
    }
    return $matches[0]
}

function Get-DefaultProfileName($Entry) {
    if ($Entry.PSObject.Properties["profile"] -and -not [string]::IsNullOrWhiteSpace([string]$Entry.profile)) {
        return [string]$Entry.profile
    }
    return [string]$Entry.id
}

function ConvertTo-KntRepositoryRelativePath([string]$Path) {
    return ([string]$Path).Replace('\', '/').TrimStart('/')
}

function Get-KntRepositoryPathKey([string]$Path) {
    $canonical = ConvertTo-KntRepositoryRelativePath $Path
    if ($env:OS -eq "Windows_NT") { return $canonical.ToLowerInvariant() }
    return $canonical
}

function Test-KntRepositoryRelativePathSyntax([string]$Path) {
    $value = [string]$Path
    if ([string]::IsNullOrWhiteSpace($value)) { return $false }
    if ([IO.Path]::IsPathRooted($value) -or $value -match '^(?:[A-Za-z]:)?[\\/]') { return $false }
    $normalized = ConvertTo-KntRepositoryRelativePath $value
    if ($normalized -match '(^|/)\.\.(/|$)' -or $normalized -eq '.') { return $false }
    return $true
}

function Get-DefaultTemplateRepositoryPaths([string]$DefaultId) {
    $templateRoot = Join-Path $BaseDir ("templates/defaults/" + $DefaultId)
    if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) { return @() }
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($templateFile in @(Get-ChildItem -LiteralPath $templateRoot -Recurse -File -Force)) {
        $relative = ConvertTo-BaseRelativePath -Root $templateRoot -AbsolutePath $templateFile.FullName
        $repositoryRelative = if ($relative -like ".github/*") { $relative } else { "project/$relative" }
        [void]$paths.Add((ConvertTo-KntRepositoryRelativePath $repositoryRelative))
    }
    return @($paths | Sort-Object -Unique)
}

function Get-DefaultTrustedOwnedPaths($Catalog, [string]$DefaultId) {
    $entry = Find-AnyDefaultCatalogEntry -Catalog $Catalog -Identifier $DefaultId
    $paths = @{}
    foreach ($path in @(Get-DefaultTemplateRepositoryPaths -DefaultId ([string]$entry.id))) {
        $paths[(Get-KntRepositoryPathKey $path)] = (ConvertTo-KntRepositoryRelativePath $path)
    }
    $retiredPaths = if ($entry.PSObject.Properties["retired_paths"]) { @($entry.retired_paths) } else { @() }
    foreach ($retired in $retiredPaths) {
        $canonical = ConvertTo-KntRepositoryRelativePath ([string]$retired)
        $paths[(Get-KntRepositoryPathKey $canonical)] = $canonical
    }
    return $paths
}

function Get-DefaultOptions([string]$CommandName) {
    $profiles = New-Object System.Collections.Generic.List[string]
    $defaults = New-Object System.Collections.Generic.List[string]
    $apply = $false
    $values = @($RemainingArgs)
    for ($index = 0; $index -lt $values.Count; $index++) {
        $value = [string]$values[$index]
        if ([string]::IsNullOrWhiteSpace($value)) { continue }
        if ($value -eq "--apply") {
            if ($CommandName -ne "migrate") { throw "Unknown $CommandName option: $value" }
            $apply = $true
            continue
        }
        if ($value -eq "--profile" -or $value -eq "--default") {
            if ($index + 1 -ge $values.Count -or [string]::IsNullOrWhiteSpace([string]$values[$index + 1])) {
                throw "$CommandName requires a value after $value"
            }
            $optionName = $value
            $value = [string]$values[++$index]
        }
        elseif ($value -like "--profile=*") {
            $optionName = "--profile"
            $value = $value.Substring("--profile=".Length)
        }
        elseif ($value -like "--default=*") {
            $optionName = "--default"
            $value = $value.Substring("--default=".Length)
        }
        else {
            throw "Unknown $CommandName option: $value"
        }

        if ($optionName -eq "--profile") {
            if ($value -notin $profiles) { [void]$profiles.Add($value) }
        }
        else {
            if ($value -notin $defaults) { [void]$defaults.Add($value) }
        }
    }
    return [pscustomobject]@{ profiles = @($profiles); defaults = @($defaults); apply = $apply }
}

function Resolve-DefaultSelections($Options, $Catalog, [bool]$RequireProfile, [string[]]$ExistingSurfaces = @(), [string[]]$ExistingProfiles = @()) {
    $profileEntries = @()
    foreach ($profileName in @($Options.profiles)) {
        $profileEntries += Find-DefaultCatalogEntry -Catalog $Catalog -Identifier ([string]$profileName) -Kind "surface"
    }
    if ($RequireProfile -and $profileEntries.Count -eq 0) {
        throw "init requires at least one --profile"
    }

    $toolEntries = @()
    foreach ($defaultName in @($Options.defaults)) {
        $toolEntries += Find-DefaultCatalogEntry -Catalog $Catalog -Identifier ([string]$defaultName) -Kind "tool"
    }
    $selectedSurfaces = @(Get-DefaultCompatibilityKeys -Catalog $Catalog -ProfileIds @($ExistingProfiles + @($Options.profiles)) -SurfaceIds $ExistingSurfaces -ProfileEntries $profileEntries)
    foreach ($tool in $toolEntries) {
        $compatibilityError = Get-DefaultCompatibilityError -Entry $tool -SelectedSurfaces $selectedSurfaces
        if ($compatibilityError) { throw $compatibilityError }
    }
    return [pscustomobject]@{ profileEntries = @($profileEntries); toolEntries = @($toolEntries); options = $Options }
}

function Get-SelectedInitProfiles {
    $catalog = Get-DefaultCatalog
    $selection = Resolve-DefaultSelections -Options (Get-DefaultOptions "init") -Catalog $catalog -RequireProfile $true
    return $selection
}

function Get-DefaultStateEntry($State) {
    return [pscustomobject]@{ state = $State }
}

function Add-RepositoryShapeTool($ToolIds, $ToolStates, [string]$ToolId, [string]$State = "DEFAULT") {
    if ($ToolId -notin $ToolIds) { [void]$ToolIds.Add($ToolId) }
    if (-not $ToolStates.ContainsKey($ToolId) -or $State -eq "OVERRIDE") {
        $ToolStates[$ToolId] = $State
    }
}

function Add-RepositoryShapeSurface($SurfaceIds, $SurfaceStates, [string]$SurfaceId, [string]$State = "OVERRIDE") {
    if ($SurfaceId -notin $SurfaceIds) { [void]$SurfaceIds.Add($SurfaceId) }
    if (-not $SurfaceStates.ContainsKey($SurfaceId) -or $State -eq "OVERRIDE") {
        $SurfaceStates[$SurfaceId] = $State
    }
}

function Get-ShapeCompatibleSurfaceValues($Catalog, [string[]]$SurfaceIds) {
    return @(Get-DefaultCompatibilityKeys -Catalog $Catalog -SurfaceIds $SurfaceIds)
}

function Test-IsBaseVerificationWorkflow([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $leaf = Split-Path -Leaf $Path
    if ($leaf -notin @("verify.yml", "verify.yaml")) { return $false }
    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path
    return $text -match "(?im)\.kinotch/scripts/knt\.ps1\s+doctor" -and
        $text -match "(?im)\.kinotch/scripts/knt\.ps1\s+setup" -and
        $text -match "(?im)\.kinotch/scripts/knt\.ps1\s+verify"
}

function Get-RepositoryShape($Catalog) {
    $surfaceIds = New-Object System.Collections.Generic.List[string]
    $surfaceStates = @{}
    $toolIds = New-Object System.Collections.Generic.List[string]
    $toolStates = @{}
    $markers = New-Object System.Collections.Generic.List[string]
    $packagePath = Join-Path $Root "package.json"
    $packageText = ""
    $package = $null
    if (Test-Path -LiteralPath $packagePath -PathType Leaf) {
        $packageText = Get-Content -Raw -Encoding UTF8 $packagePath
        try { $package = $packageText | ConvertFrom-Json } catch { }
        [void]$markers.Add("package.json")
    }
    $cargoPath = Join-Path $Root "Cargo.toml"
    $cargoText = if (Test-Path -LiteralPath $cargoPath -PathType Leaf) { Get-Content -Raw -Encoding UTF8 $cargoPath } else { "" }
    if ($cargoText) { [void]$markers.Add("Cargo.toml") }
    $pythonPaths = @((Join-Path $Root "pyproject.toml"), (Join-Path $Root "requirements.txt"))
    $pythonText = ""
    foreach ($pythonPath in $pythonPaths) {
        if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
            $pythonText += Get-Content -Raw -Encoding UTF8 $pythonPath
            [void]$markers.Add((Split-Path -Leaf $pythonPath))
        }
    }
    $workflowPath = Join-Path $Root ".github/workflows"
    if (Test-Path -LiteralPath $workflowPath -PathType Container) {
        [void]$markers.Add(".github/workflows")
        $workflowFiles = @(Get-ChildItem -LiteralPath $workflowPath -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".yml", ".yaml") -and -not (Test-IsBaseVerificationWorkflow $_.FullName) })
        $workflowText = ($workflowFiles | ForEach-Object { Get-Content -Raw -Encoding UTF8 -LiteralPath $_.FullName }) -join "`n"
        if ($workflowFiles.Count -gt 0) {
            $hasVerificationGate = $workflowText -match "(?im)(npm\s+(?:run\s+)?(?:test|lint|typecheck|build)|pnpm\s+(?:test|lint|typecheck|build)|yarn\s+(?:test|lint|typecheck|build)|pytest|python\s+-m\s+(?:pytest|unittest)|cargo\s+(?:test|check|build)|knt(?:\.cmd)?\s+verify|\.kinotch/scripts/knt\.ps1\s+verify)"
            Add-RepositoryShapeTool -ToolIds $toolIds -ToolStates $toolStates -ToolId "ci-test" -State $(if ($hasVerificationGate) { "OVERRIDE" } else { "DEFAULT" })
        }
    }
    $publicPath = Join-Path $Root "public"
    $staticPath = Join-Path $Root "static"
    $hasWebAssets = (Test-Path -LiteralPath $publicPath -PathType Container) -or (Test-Path -LiteralPath $staticPath -PathType Container) -or (Test-Path -LiteralPath (Join-Path $Root "index.html") -PathType Leaf)
    $scriptsText = if ($package -and $package.scripts) { ($package.scripts | Out-String) } else { "" }
    $dependencyText = ($packageText + " " + $pythonText + " " + $cargoText).ToLowerInvariant()

    # Wrangler is also the normal Pages/static-Web toolchain. Treat it as an
    # API marker only when an application/API boundary is explicit.
    if ($dependencyText -match "(?i)\bhono\b|service\s+binding|cloudflare\s+worker") {
        Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "api"
    }
    if ($hasWebAssets -or $dependencyText -match "vite|react|vue|svelte|astro|next") {
        Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "web-app"
    }
    # knt verify is an L1 Hard Base command. Shape detection must not report it
    # as an optional Tool Default; CI remains the independent L2 candidate.
    $packageBin = $false
    if ($package -and $package.PSObject.Properties["bin"] -and $null -ne $package.bin) {
        $packageBin = $true
    }
    $packageCliScript = $false
    if ($package -and $package.PSObject.Properties["scripts"] -and $package.scripts) {
        $packageCliScript = @($package.scripts.PSObject.Properties.Name | Where-Object { $_ -match "(^|[-_:])(cli|command)$" }).Count -gt 0
    }
    $hasPythonScripts = $pythonText -match "(?im)^\s*\[(?:project\.scripts|tool\.poetry\.scripts)\]"
    $hasCargoBin = $cargoText -match "(?im)^\s*\[\[bin\]\]"
    if ($packageBin -or $packageCliScript -or $hasPythonScripts -or $hasCargoBin) {
        Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "cli"
    }
    if ($cargoText -match "egui|tauri|winit|windows|gtk") { Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "windows" }
    if ($pythonText -match "streamlit|gradio") { Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "web-app" }
    if ($dependencyText -match "mcp") { Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "mcp" }
    if ($Root -match "dev_agent|agent") { Add-RepositoryShapeSurface -SurfaceIds $surfaceIds -SurfaceStates $surfaceStates -SurfaceId "agent" }

    $scanDirectories = @("public", "static", "src", "app", "tools", "scripts", "backend", "frontend") | ForEach-Object { Join-Path $Root $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    $scanFiles = @()
    foreach ($scanDirectory in $scanDirectories) {
        $scanFiles += @(Get-ChildItem -LiteralPath $scanDirectory -Recurse -File -Force -ErrorAction SilentlyContinue)
    }
    $scanFiles += @(Get-ChildItem -LiteralPath $Root -File -Force -ErrorAction SilentlyContinue)
    $manifestPath = @(
        (Join-Path $Root "public/manifest.webmanifest"),
        (Join-Path $Root "public/manifest.json"),
        (Join-Path $Root "manifest.webmanifest"),
        (Join-Path $Root "manifest.json")
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    $workerFiles = @($scanFiles | Where-Object { $_.Name -match "service-worker|sw\.js$" })
    if ($manifestPath -and $workerFiles.Count -gt 0) { Add-RepositoryShapeTool -ToolIds $toolIds -ToolStates $toolStates -ToolId "pwa" -State "OVERRIDE" }
    $integrityDirectories = @("src", "app", "tools", "scripts", "backend", "frontend") |
        ForEach-Object { Join-Path $Root $_ } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    $integrityFiles = @()
    foreach ($integrityDirectory in $integrityDirectories) {
        $integrityFiles += @(Get-ChildItem -LiteralPath $integrityDirectory -Recurse -File -Force -ErrorAction SilentlyContinue)
    }
    $generatedFiles = @($integrityFiles | Where-Object { $_.Name -match "(^generated|\.generated\.|generated\.)" })
    $integrityText = $scriptsText
    foreach ($scanFile in @($integrityFiles | Where-Object { $_.Extension -in @(".ps1", ".mjs", ".js", ".py", ".rs", ".toml", ".yml", ".yaml") })) {
        $integrityText += "`n" + (Get-Content -Raw -Encoding UTF8 -LiteralPath $scanFile.FullName -ErrorAction SilentlyContinue)
    }
    $hasIntegrityEvidence = $integrityText -match "(?i)sha[-_]?256|source[_-]?fingerprint|stale|generated.*check|check.*generated|snapshot.*check"
    if ($generatedFiles.Count -gt 0 -or $hasIntegrityEvidence) {
        Add-RepositoryShapeTool -ToolIds $toolIds -ToolStates $toolStates -ToolId "generated-integrity" -State $(if ($hasIntegrityEvidence) { "OVERRIDE" } else { "DEFAULT" })
    }

    # A filename or text marker is not enough to make a Tool Default relevant
    # to the detected repository shape.  Filter candidates through the same
    # compatibility rule used by init/migrate so an Agent repository, for
    # example, is not offered generated-integrity merely because its own
    # evidence records contain the words "sha256" or "stale".
    $shapeSurfaceValues = @(Get-ShapeCompatibleSurfaceValues -Catalog $Catalog -SurfaceIds @($surfaceIds))
    $compatibleToolIds = New-Object System.Collections.Generic.List[string]
    $compatibleToolStates = @{}
    foreach ($toolId in @($toolIds | Select-Object -Unique)) {
        $entry = Find-DefaultCatalogEntry -Catalog $Catalog -Identifier $toolId -Kind "tool"
        if (-not (Get-DefaultCompatibilityError -Entry $entry -SelectedSurfaces $shapeSurfaceValues)) {
            [void]$compatibleToolIds.Add($toolId)
            $state = if ($toolStates.ContainsKey($toolId)) { [string]$toolStates[$toolId] } else { "DEFAULT" }
            $compatibleToolStates[$toolId] = $state
        }
    }

    return [pscustomobject]@{
        markers = @($markers | Select-Object -Unique)
        surfaceIds = @($surfaceIds | Select-Object -Unique)
        surfaceStates = $surfaceStates
        toolIds = @($compatibleToolIds | Select-Object -Unique)
        toolStates = $compatibleToolStates
    }
}

function Get-MigrateProfileEntries($Manifest, $Catalog, $Options, $Shape) {
    $requested = @($Options.profiles)
    if ($requested.Count -eq 0) {
        if ($Manifest -and $Manifest.PSObject.Properties["profiles"] -and @($Manifest.profiles).Count -gt 0) {
            $requested = @($Manifest.profiles | ForEach-Object { [string]$_ })
        }
        elseif ($Manifest -and -not [string]::IsNullOrWhiteSpace([string]$Manifest.profile)) {
            $requested = @([string]$Manifest.profile)
        }
        elseif ($Shape) {
            $requested = @($Shape.surfaceIds)
        }
    }
    $entries = @()
    foreach ($profileName in @($requested | Select-Object -Unique)) {
        try {
            $entries += Find-DefaultCatalogEntry -Catalog $Catalog -Identifier $profileName -Kind "surface"
        }
        catch {
            if (@($Options.profiles) -contains $profileName) { throw }
            Write-Host "[migrate] WARN profile '$profileName' is not in the Default catalog; skipped" -ForegroundColor Yellow
        }
    }
    return @($entries)
}

function Get-ManifestSurfaceIds($Manifest) {
    if (-not $Manifest -or -not $Manifest.PSObject.Properties["surfaces"]) { return @() }
    return @($Manifest.surfaces.PSObject.Properties | Where-Object { $_.Value -eq $true } | ForEach-Object { [string]$_.Name } | Select-Object -Unique)
}

function Get-MigrateToolEntries($Manifest, $Catalog, $Options, $Shape) {
    if (@($Options.defaults).Count -gt 0) {
        $existingSurfaces = if ($Manifest) { @(Get-ManifestSurfaceIds -Manifest $Manifest) } else { @() }
        $existingProfiles = if ($Manifest -and $Manifest.PSObject.Properties["profiles"] -and @($Manifest.profiles).Count -gt 0) {
            @($Manifest.profiles | ForEach-Object { [string]$_ })
        }
        elseif ($Manifest -and -not [string]::IsNullOrWhiteSpace([string]$Manifest.profile)) {
            @([string]$Manifest.profile)
        }
        else { @() }
        return @(Resolve-DefaultSelections -Options $Options -Catalog $Catalog -RequireProfile $false -ExistingSurfaces $existingSurfaces -ExistingProfiles $existingProfiles).toolEntries
    }

    if ($Shape -and @($Shape.toolIds).Count -gt 0) {
        $entries = @()
        foreach ($candidateId in @($Shape.toolIds)) {
            $entries += Find-DefaultCatalogEntry -Catalog $Catalog -Identifier $candidateId -Kind "tool"
        }
        return @($entries)
    }

    $candidateIds = New-Object System.Collections.Generic.List[string]
    $baseVerifyWorkflow = Join-Path $Root ".github/workflows/verify.yml"
    if ((Test-Path -LiteralPath $baseVerifyWorkflow -PathType Leaf) -and -not (Test-IsBaseVerificationWorkflow $baseVerifyWorkflow)) {
        [void]$candidateIds.Add("ci-test")
    }
    $generatedCandidates = @(Get-ChildItem -LiteralPath (Join-Path $Root "project") -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "(^generated|\.generated\.|generated\.)"
    })
    if ($generatedCandidates.Count -gt 0) { [void]$candidateIds.Add("generated-integrity") }

    $entries = @()
    foreach ($candidateId in @($candidateIds | Select-Object -Unique)) {
        $entries += Find-DefaultCatalogEntry -Catalog $Catalog -Identifier $candidateId -Kind "tool"
    }
    return @($entries)
}

function Get-MigrateRecommendedState($Entry, $Shape) {
    if ([string]$Entry.kind -eq "surface" -and $Shape -and $Shape.surfaceStates -and $Shape.surfaceStates.ContainsKey([string]$Entry.id)) {
        return [string]$Shape.surfaceStates[[string]$Entry.id]
    }
    if ([string]$Entry.kind -eq "tool" -and $Shape -and $Shape.toolStates -and $Shape.toolStates.ContainsKey([string]$Entry.id)) {
        return [string]$Shape.toolStates[[string]$Entry.id]
    }
    return "DEFAULT"
}

function Write-KntJsonFile([string]$Path, $Value) {
    $json = ConvertTo-Json $Value -Depth 20
    $safePath = Assert-KntSafeWritePath -Root $Root -Candidate $Path -Description "JSON output"
    [IO.File]::WriteAllText($safePath, $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-KntBaseVersion {
    return (Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $BaseDir "BASE_VERSION")).Trim()
}

function Get-DefaultMaterializedFileMetadata($Plan) {
    $metadata = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($Plan | Where-Object { $null -ne $_ -and $null -ne $_.template })) {
        if (-not (Test-Path -LiteralPath $item.destination -PathType Leaf)) { continue }
        [void]$metadata.Add([pscustomobject]@{
            path = (ConvertTo-BaseRelativePath -Root $Root -AbsolutePath $item.destination)
            sha256 = (Get-BaseFileHash -Path $item.destination)
        })
    }
    return @($metadata.ToArray())
}

function Set-DefaultProvenance($PackEntry, $Plan) {
    $planItems = @($Plan | Where-Object { $null -ne $_ -and $null -ne $_.template })
    if ($planItems.Count -eq 0) { return $false }
    $metadata = @(Get-DefaultMaterializedFileMetadata -Plan $planItems)
    if ($metadata.Count -ne $planItems.Count) { return $false }
    $before = ConvertTo-Json $PackEntry -Depth 20 -Compress
    $PackEntry | Add-Member -NotePropertyName source_base_version -NotePropertyValue (Get-KntBaseVersion) -Force
    $PackEntry | Add-Member -NotePropertyName materialized_files -NotePropertyValue $metadata -Force
    $after = ConvertTo-Json $PackEntry -Depth 20 -Compress
    return ($before -ne $after)
}

function Clear-DefaultProvenance($PackEntry) {
    $changed = $false
    foreach ($propertyName in @("source_base_version", "materialized_files")) {
        if ($PackEntry.PSObject.Properties[$propertyName]) {
            $PackEntry.PSObject.Properties.Remove($propertyName)
            $changed = $true
        }
    }
    return $changed
}

function Finalize-DefaultImplementation([string]$DefaultId, $Manifest, [string]$ProjectRoot) {
    if ($DefaultId -eq "pwa") {
        $pwaManifestPath = Join-Path $ProjectRoot "public/manifest.webmanifest"
        if (-not (Test-Path -LiteralPath $pwaManifestPath -PathType Leaf)) { return }
        $pwaManifest = Get-KntJson -Path $pwaManifestPath
        $projectName = [string]$Manifest.project.name
        if ([string]::IsNullOrWhiteSpace($projectName)) { $projectName = "KiNoTch. Project" }
        $pwaManifest.name = $projectName
        $pwaManifest.short_name = $projectName
        if ([string]::IsNullOrWhiteSpace([string]$pwaManifest.start_url) -or [string]$pwaManifest.start_url -match '^[\\/]|^[a-zA-Z][a-zA-Z0-9+.-]*:') {
            $pwaManifest.start_url = "."
        }
        if ([string]::IsNullOrWhiteSpace([string]$pwaManifest.display)) { $pwaManifest.display = "standalone" }
        Write-KntJsonFile -Path $pwaManifestPath -Value $pwaManifest
        return
    }
    if ($DefaultId -eq "ci-test") {
        $workflowPath = Join-Path $Root ".github/workflows/kinotch-default.yml"
        if (-not (Test-Path -LiteralPath $workflowPath -PathType Leaf)) { return }
        $runner = if ([bool](Get-KntJsonProperty $Manifest.surfaces "gui_windows")) { "windows-latest" } else { "ubuntu-latest" }
        $workflow = @"
name: KiNoTch Default Verify

on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: $runner
    defaults:
      run:
        shell: pwsh
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - name: Base / project diagnostics
        run: ./.kinotch/scripts/knt.ps1 doctor
      - name: Project setup
        run: ./.kinotch/scripts/knt.ps1 setup
      - name: Project verification
        run: ./.kinotch/scripts/knt.ps1 verify
"@
        $safeWorkflowPath = Assert-KntSafeWritePath -Root $Root -Candidate $workflowPath -Description "ci-test workflow"
        [IO.File]::WriteAllText($safeWorkflowPath, $workflow.TrimStart(), (New-Object System.Text.UTF8Encoding($false)))
    }
}

function Get-DefaultImplementationPlan([string]$DefaultId, [string]$ProjectRoot, [string]$Kind = "Tool", $ExistingState = $null) {
    $templateRoot = Join-Path $BaseDir ("templates/defaults/" + $DefaultId)
    if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) { return @() }
    $catalog = Get-DefaultCatalog
    $trustedOwnedPaths = Get-DefaultTrustedOwnedPaths -Catalog $catalog -DefaultId $DefaultId
    $recordedHashes = @{}
    if ($ExistingState -and $ExistingState.PSObject.Properties["materialized_files"]) {
        foreach ($recorded in @($ExistingState.materialized_files)) {
            if (-not [string]::IsNullOrWhiteSpace([string]$recorded.path)) {
                $recordedHashes[[string]$recorded.path] = [string]$recorded.sha256
            }
        }
    }
    $plan = New-Object System.Collections.Generic.List[object]
    $templateRepositoryPaths = New-Object System.Collections.Generic.HashSet[string]
    foreach ($templateFile in @(Get-ChildItem -LiteralPath $templateRoot -Recurse -File -Force | Sort-Object FullName)) {
        $relative = ConvertTo-BaseRelativePath -Root $templateRoot -AbsolutePath $templateFile.FullName
        if ($relative -like ".github/*") {
            $destination = Join-Path $Root $relative
        }
        else {
            $destination = Join-Path $ProjectRoot $relative
        }
        $repositoryRelative = ConvertTo-BaseRelativePath -Root $Root -AbsolutePath $destination
        [void]$templateRepositoryPaths.Add($repositoryRelative)
        $status = "MISSING"
        if (Test-Path -LiteralPath $destination) {
            $currentHash = $null
            $templateHash = Get-BaseFileHash -Path $templateFile.FullName
            try {
                $currentHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { Get-BaseFileHash -Path $destination } else { $null }
            }
            catch {
                $currentHash = $null
            }
            if ($recordedHashes.ContainsKey($repositoryRelative)) {
                if ($currentHash -ne $recordedHashes[$repositoryRelative]) {
                    $status = "CONFLICT"
                }
                elseif ($currentHash -eq $templateHash) {
                    $status = "IDENTICAL"
                }
                else {
                    $status = "UPGRADABLE"
                }
            }
            else {
                $status = if ($currentHash -eq $templateHash) { "IDENTICAL" } else { "CONFLICT" }
            }
        }
        [void]$plan.Add([pscustomobject]@{
            default_id = $DefaultId
            kind = $Kind
            relative = $relative
            repository_relative = $repositoryRelative
            template = $templateFile.FullName
            destination = $destination
            status = $status
            action = "copy"
        })
    }
    foreach ($recordedPath in @($recordedHashes.Keys)) {
        if ($templateRepositoryPaths.Contains($recordedPath)) { continue }
        $recordedKey = Get-KntRepositoryPathKey $recordedPath
        if (-not $trustedOwnedPaths.ContainsKey($recordedKey)) {
            [void]$plan.Add([pscustomobject]@{
                default_id = $DefaultId
                kind = $Kind
                relative = $recordedPath
                repository_relative = $recordedPath
                template = $null
                destination = $null
                status = "UNTRUSTED"
                action = "remove"
            })
            continue
        }
        try {
            $destination = Resolve-KntContainedPath -BaseRoot $Root -RelativePath $recordedPath -Description "Default '$DefaultId' recorded path" -AllowRoot
        }
        catch {
            [void]$plan.Add([pscustomobject]@{
                default_id = $DefaultId
                kind = $Kind
                relative = $recordedPath
                repository_relative = $recordedPath
                template = $null
                destination = $null
                status = "CONFLICT"
                action = "remove"
            })
            continue
        }
        $currentHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { Get-BaseFileHash -Path $destination } else { $null }
        $status = if ($null -eq $currentHash -or $currentHash -eq $recordedHashes[$recordedPath]) { "STALE_UNCHANGED" } else { "CONFLICT" }
        [void]$plan.Add([pscustomobject]@{
            default_id = $DefaultId
            kind = $Kind
            relative = $recordedPath
            repository_relative = $recordedPath
            template = $null
            destination = $destination
            status = $status
            action = "remove"
        })
    }
    return @($plan.ToArray())
}

function Get-DefaultRemovalPlan([string]$DefaultId, $ExistingState, [string]$Kind = "Tool") {
    $plan = New-Object System.Collections.Generic.List[object]
    if (-not $ExistingState -or -not $ExistingState.PSObject.Properties["materialized_files"]) { return @() }
    $catalog = Get-DefaultCatalog
    $trustedOwnedPaths = Get-DefaultTrustedOwnedPaths -Catalog $catalog -DefaultId $DefaultId
    foreach ($recorded in @($ExistingState.materialized_files)) {
        $recordedPath = [string]$recorded.path
        $recordedKey = Get-KntRepositoryPathKey $recordedPath
        if (-not $trustedOwnedPaths.ContainsKey($recordedKey)) {
            [void]$plan.Add([pscustomobject]@{
                default_id = $DefaultId
                kind = $Kind
                relative = $recordedPath
                repository_relative = $recordedPath
                template = $null
                destination = $null
                status = "UNTRUSTED"
                action = "remove"
            })
            continue
        }
        try {
            $destination = Resolve-KntContainedPath -BaseRoot $Root -RelativePath $recordedPath -Description "Default '$DefaultId' recorded path" -AllowRoot
        }
        catch {
            [void]$plan.Add([pscustomobject]@{
                default_id = $DefaultId
                kind = $Kind
                relative = $recordedPath
                repository_relative = $recordedPath
                template = $null
                destination = $null
                status = "CONFLICT"
                action = "remove"
            })
            continue
        }
        $currentHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { Get-BaseFileHash -Path $destination } else { $null }
        $status = if ($null -eq $currentHash -or $currentHash -eq [string]$recorded.sha256) { "STALE_UNCHANGED" } else { "CONFLICT" }
        [void]$plan.Add([pscustomobject]@{
            default_id = $DefaultId
            kind = $Kind
            relative = $recordedPath
            repository_relative = $recordedPath
            template = $null
            destination = $destination
            status = $status
            action = "remove"
        })
    }
    return @($plan.ToArray())
}

function Apply-DefaultImplementationPlan($Plan, [System.Collections.Generic.List[string]]$ConflictingDefaults) {
    $planItems = @($Plan | Where-Object { $null -ne $_ })
    if ($planItems.Count -eq 0) { return }
    Assert-RepositoryWriteAllowed "Default materialization"
    $defaultId = [string]$planItems[0].default_id
    $kind = [string]$planItems[0].kind
    $conflicts = @($planItems | Where-Object { [string]$_.status -in @("CONFLICT", "UNTRUSTED") })
    if ($conflicts.Count -gt 0) {
        if ($null -ne $ConflictingDefaults -and $defaultId -notin $ConflictingDefaults) { [void]$ConflictingDefaults.Add($defaultId) }
        foreach ($conflict in $conflicts) {
            $reason = if ([string]$conflict.status -eq "UNTRUSTED") { "untrusted provenance path" } else { "conflicting existing path" }
            Write-Knt "$kind Default '$defaultId' found $reason`: $($conflict.relative); state OVERRIDE"
        }
        Write-Knt "$kind Default '$defaultId' no Default files were materialized because the implementation plan contains conflicts"
        return
    }
    foreach ($item in $planItems) {
        if ([string]$item.action -eq "remove") {
            if ([string]$item.status -eq "STALE_UNCHANGED" -and $item.destination -and (Test-Path -LiteralPath $item.destination -PathType Leaf)) {
                $safeDestination = Assert-KntSafeWritePath -Root $Root -Candidate $item.destination -Description "Default '$defaultId' cleanup"
                Remove-Item -LiteralPath $safeDestination -Force
                Write-Knt "$kind Default '$defaultId' removed stale path: $($item.relative)"
            }
            continue
        }
        if ([string]$item.status -eq "IDENTICAL") {
            Write-Knt "$kind Default '$defaultId' preserved identical path: $($item.relative)"
            continue
        }
        $safeDestination = Assert-KntSafeWritePath -Root $Root -Candidate $item.destination -Description "Default '$defaultId' materialization"
        $parent = Split-Path -Parent $safeDestination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $item.template -Destination $safeDestination -Force
        Write-Knt "$kind Default '$defaultId' materialized: $($item.relative)"
    }
    return [pscustomobject]@{ default_id = $defaultId; conflict = $false }
}

function Invoke-GeneratedDefaultScript([string]$ScriptRelativePath, [string]$CommandLabel) {
    $projectRoot = Join-Path $Root "project"
    $scriptPath = Join-Path $projectRoot $ScriptRelativePath
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        Write-Host "[$CommandLabel] MISSING project/$ScriptRelativePath" -ForegroundColor Red
        return 1
    }
    $powerShell = (Get-Command pwsh -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ([string]::IsNullOrWhiteSpace($powerShell)) {
        $powerShell = (Get-Command powershell -ErrorAction Stop | Select-Object -First 1).Source
    }
    & $powerShell -NoProfile -ExecutionPolicy Bypass -File $scriptPath
    if ($null -ne $LASTEXITCODE) { return $LASTEXITCODE }
    return 0
}

function Invoke-PwaCheck {
    return Invoke-GeneratedDefaultScript -ScriptRelativePath "tools/pwa-check.ps1" -CommandLabel "pwa-check"
}

function Invoke-GeneratedIntegrityCheck {
    return Invoke-GeneratedDefaultScript -ScriptRelativePath "tools/check-generated.ps1" -CommandLabel "generated-integrity"
}

function Invoke-Init {
    if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        Write-Host "[init] Repository is already initialized: project/project.json" -ForegroundColor Yellow
        return 1
    }

    Assert-RepositoryWriteAllowed "init"

    $catalog = Get-DefaultCatalog
    $selection = Get-SelectedInitProfiles
    $profileEntries = @($selection.profileEntries)
    $toolEntries = @($selection.toolEntries)
    $profiles = @($profileEntries | ForEach-Object { Get-DefaultProfileName $_ })
    $projectRoot = Join-Path $Root "project"
    if (Test-Path -LiteralPath $projectRoot -PathType Container) {
        $existing = @(Get-ChildItem -LiteralPath $projectRoot -Force)
        if ($existing.Count -gt 0) {
            Write-Host "[init] Project directory is not empty; refusing to overwrite Project files" -ForegroundColor Yellow
            return 1
        }
    }

    $templateRoot = Join-Path $BaseDir "templates/project"
    if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
        throw "Project template not found: $templateRoot"
    }
    $safeProjectRoot = Assert-KntSafeWritePath -Root $Root -Candidate $projectRoot -Description "Project materialization" -AllowRoot
    New-Item -ItemType Directory -Path $safeProjectRoot -Force | Out-Null

    foreach ($templateEntry in @(Get-ChildItem -LiteralPath $templateRoot -Force)) {
        if ($templateEntry.Name -eq "README.md") {
            $destination = Join-Path $Root "README.md"
        }
        elseif ($templateEntry.Name -eq ".gitignore") {
            $destination = Join-Path $projectRoot ".gitignore"
        }
        else {
            $destination = Join-Path $projectRoot $templateEntry.Name
        }

        if (Test-Path -LiteralPath $destination) {
            if ($templateEntry.Name -eq "README.md") { continue }
            throw "Refusing to overwrite existing generated path: $destination"
        }
        $safeDestination = Assert-KntSafeWritePath -Root $Root -Candidate $destination -Description "Project template materialization"
        Copy-Item -LiteralPath $templateEntry.FullName -Destination $safeDestination -Recurse -Force
    }

    $manifest = Get-KntJson -Path $ManifestPath
    $manifest.project.name = (Split-Path -Leaf $Root.TrimEnd([char[]]@("/", "\")))
    if ([string]::IsNullOrWhiteSpace($manifest.project.name)) { $manifest.project.name = "kinotch-project" }
    $defaultIds = @($profileEntries + $toolEntries | ForEach-Object { [string]$_.id })
    $manifest.project.description = "KiNoTch. Project initialized with Default Packs: " + ($defaultIds -join ", ")
    $manifest.profile = $profiles[0]
    $manifest | Add-Member -NotePropertyName profiles -NotePropertyValue $profiles -Force
    $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force

    $surfaceNames = New-Object System.Collections.Generic.List[string]
    $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{} }
    $conflictingDefaults = New-Object System.Collections.Generic.List[string]
    $materializationPlans = @{}
    foreach ($profileEntry in $profileEntries) {
        $profileName = Get-DefaultProfileName $profileEntry
        $profilePath = Join-Path $BaseDir ("profiles/" + $profileName + ".json")
        $profile = Get-KntJson -Path $profilePath
        foreach ($surface in @($profile.surfaces.PSObject.Properties | Where-Object { $_.Value -eq $true })) {
            if ($surface.Name -notin $surfaceNames) { [void]$surfaceNames.Add([string]$surface.Name) }
        }
        $defaults.packs | Add-Member -NotePropertyName ([string]$profileEntry.id) -NotePropertyValue (Get-DefaultStateEntry "DEFAULT") -Force
        $plan = Get-DefaultImplementationPlan -DefaultId ([string]$profileEntry.id) -ProjectRoot $projectRoot -Kind "Surface"
        $materializationPlans[[string]$profileEntry.id] = @($plan)
        [void](Apply-DefaultImplementationPlan -Plan $plan -ConflictingDefaults $conflictingDefaults)
    }
    foreach ($toolEntry in $toolEntries) {
        $defaults.packs | Add-Member -NotePropertyName ([string]$toolEntry.id) -NotePropertyValue (Get-DefaultStateEntry "DEFAULT") -Force
        $plan = Get-DefaultImplementationPlan -DefaultId ([string]$toolEntry.id) -ProjectRoot $projectRoot -Kind "Tool"
        $materializationPlans[[string]$toolEntry.id] = @($plan)
        [void](Apply-DefaultImplementationPlan -Plan $plan -ConflictingDefaults $conflictingDefaults)
    }
    foreach ($conflictingDefault in @($conflictingDefaults | Select-Object -Unique)) {
        $defaults.packs.$conflictingDefault.state = "OVERRIDE"
    }
    $manifest.runtime.modules = @()
    foreach ($surface in @($manifest.surfaces.PSObject.Properties)) {
        $surface.Value = ($surface.Name -in $surfaceNames)
    }
    foreach ($entry in @($profileEntries + $toolEntries)) {
        $packEntry = $defaults.packs.PSObject.Properties[[string]$entry.id]
        if ($packEntry -and [string](Get-KntJsonProperty $packEntry.Value "state") -eq "DEFAULT") {
            Finalize-DefaultImplementation -DefaultId ([string]$entry.id) -Manifest $manifest -ProjectRoot $projectRoot
            [void](Set-DefaultProvenance -PackEntry $packEntry.Value -Plan $materializationPlans[[string]$entry.id])
        }
    }
    Write-KntJsonFile -Path $ManifestPath -Value $manifest
    Write-KntJsonFile -Path (Join-Path $projectRoot "defaults.json") -Value $defaults
    Write-Knt "Initialized Project with Default Packs: $($defaultIds -join ', ')"
    return 0
}

function Invoke-Migrate($Manifest) {
    $options = Get-DefaultOptions "migrate"
    $catalog = Get-DefaultCatalog
    $shape = Get-RepositoryShape -Catalog $catalog
    if (-not $Manifest) {
        Write-Knt ("Detected repository markers: " + ($(if ($shape.markers.Count) { $shape.markers -join ", " } else { "(none)" })))
        Write-Knt ("Detected Surface candidates: " + ($(if ($shape.surfaceIds.Count) { $shape.surfaceIds -join ", " } else { "(none)" })))
        Write-Knt ("Detected Tool candidates: " + ($(if ($shape.toolIds.Count) { $shape.toolIds -join ", " } else { "(none)" })))
    }
    $profileEntries = @(Get-MigrateProfileEntries -Manifest $Manifest -Catalog $catalog -Options $options -Shape $shape)
    $toolEntries = @(Get-MigrateToolEntries -Manifest $Manifest -Catalog $catalog -Options $options -Shape $shape)
    $manifestSurfaceIds = if ($Manifest) { @(Get-ManifestSurfaceIds -Manifest $Manifest) } else { @() }
    $manifestProfileIds = if ($Manifest) {
        if ($Manifest.PSObject.Properties["profiles"] -and @($Manifest.profiles).Count -gt 0) { @($Manifest.profiles | ForEach-Object { [string]$_ }) }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$Manifest.profile)) { @([string]$Manifest.profile) }
        else { @() }
    }
    else { @() }
    $selectedSurfaceValues = @(Get-DefaultCompatibilityKeys -Catalog $Catalog -ProfileIds @($manifestProfileIds + @($Options.profiles)) -SurfaceIds $manifestSurfaceIds -ProfileEntries $profileEntries)
    if ($Manifest) {
        foreach ($profileEntry in @($profileEntries)) {
            $requiredSurfaces = @($profileEntry.compatible_surfaces)
            if ($requiredSurfaces.Count -eq 0) { continue }
            $enabled = @($requiredSurfaces | Where-Object { $_ -in $manifestSurfaceIds }).Count -gt 0
            if (-not $enabled) {
                $surfaceWarning = "Surface Default '$($profileEntry.id)' is NOT ENABLED IN MANIFEST"
                if ($options.apply) { throw "$surfaceWarning; migrate --apply will not add a Surface automatically" }
                Write-Host "[migrate] WARN $surfaceWarning; dry-run only" -ForegroundColor Yellow
            }
        }
    }
    foreach ($toolEntry in $toolEntries) {
        $compatibilityError = Get-DefaultCompatibilityError -Entry $toolEntry -SelectedSurfaces $selectedSurfaceValues
        if ($compatibilityError) { throw $compatibilityError }
    }
    $selectedEntries = @($profileEntries + $toolEntries)

    $projectRoot = Join-Path $Root "project"
    $defaultsRelative = Get-ManifestPathValue $Manifest "defaults" "defaults.json"
    $defaultsPath = if ($Manifest) {
        Resolve-KntManifestProjectPath -Manifest $Manifest -Name "defaults" -Default "defaults.json"
    }
    else {
        Join-Path $projectRoot $defaultsRelative
    }
    $defaultsSchema = Get-KntJson -Path (Join-Path $BaseDir "schemas/defaults.schema.json")
    $defaults = $null
    $createdDefaults = $false
    if (Test-Path -LiteralPath $defaultsPath -PathType Leaf) {
        $defaults = Get-KntJson -Path $defaultsPath
        $defaultErrors = @(Test-KntSchema -Data $defaults -Schema $defaultsSchema -Path $defaultsRelative)
        if ($defaultErrors.Count -gt 0) {
            throw "Default state validation failed: " + ($defaultErrors -join "; ")
        }
        foreach ($packProperty in @($defaults.packs.PSObject.Properties)) {
            [void](Find-AnyDefaultCatalogEntry -Catalog $catalog -Identifier ([string]$packProperty.Name))
        }
    }
    else {
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{} }
        $createdDefaults = $true
    }

    $changedDefaults = $false
    $conflictingDefaults = New-Object System.Collections.Generic.List[string]
    $materializationPlans = @{}
    $disabledEntries = New-Object System.Collections.Generic.List[object]
    foreach ($packProperty in @($defaults.packs.PSObject.Properties)) {
        $packState = [string](Get-KntJsonProperty $packProperty.Value "state")
        if ($packState -ne "DISABLED") { continue }
        $disabledEntry = Find-AnyDefaultCatalogEntry -Catalog $catalog -Identifier ([string]$packProperty.Name)
        [void]$disabledEntries.Add([pscustomobject]@{ entry = $disabledEntry; property = $packProperty })
    }
    if ($selectedEntries.Count -eq 0 -and $disabledEntries.Count -eq 0) {
        Write-Knt "No Default candidates detected. Use --profile <surface> or --default <tool-default>."
        return 0
    }
    foreach ($entry in $selectedEntries) {
        $packName = [string]$entry.id
        $packProperty = $defaults.packs.PSObject.Properties[$packName]
        if ($packProperty) {
            $state = [string](Get-KntJsonProperty $packProperty.Value "state")
            Write-Knt "Candidate Default Pack '$packName': preserved state $state"
        }
        else {
            $state = Get-MigrateRecommendedState -Entry $entry -Shape $shape
            $suffix = if ($state -eq "OVERRIDE") { " (existing equivalent detected)" } else { "" }
            Write-Knt "Candidate Default Pack '$packName': state $state$suffix"
            if ($options.apply) {
                $defaults.packs | Add-Member -NotePropertyName $packName -NotePropertyValue ([pscustomobject]@{ state = $state }) -Force
                $changedDefaults = $true
            }
        }
    }

    $disabledPlans = @{}
    foreach ($disabled in @($disabledEntries.ToArray())) {
        $defaultId = [string]$disabled.entry.id
        $plan = @(Get-DefaultRemovalPlan -DefaultId $defaultId -ExistingState $disabled.property.Value -Kind $(if ([string]$disabled.entry.kind -eq "surface") { "Surface" } else { "Tool" }))
        $disabledPlans[$defaultId] = $plan
        if ($plan.Count -eq 0) {
            Write-Knt "$(if ([string]$disabled.entry.kind -eq 'surface') { 'Surface' } else { 'Tool' }) Default '$defaultId' is DISABLED with no tracked materialized files"
            continue
        }
        foreach ($item in $plan) {
            if ([string]$item.status -eq "STALE_UNCHANGED") {
                $actionText = if ($item.destination -and (Test-Path -LiteralPath $item.destination -PathType Leaf)) { "scheduled for removal" } else { "already absent" }
                Write-Knt "$(if ([string]$disabled.entry.kind -eq 'surface') { 'Surface' } else { 'Tool' }) Default '$defaultId' is DISABLED; ${actionText}: $($item.relative)"
            }
            else {
                Write-Knt "$(if ([string]$disabled.entry.kind -eq 'surface') { 'Surface' } else { 'Tool' }) Default '$defaultId' has a modified materialized file: $($item.relative); preserve it or mark OVERRIDE"
            }
        }
    }

    if (-not $options.apply) {
        Write-Knt "Dry run: no files changed. Re-run with --apply to record selected Default Pack states."
        return 0
    }

    Assert-RepositoryWriteAllowed "migrate --apply"

    if (-not $Manifest) {
        throw "migrate --apply requires an existing Project Manifest; dry-run completed without changing this repository"
    }

    foreach ($entry in $selectedEntries) {
        $packProperty = $defaults.packs.PSObject.Properties[[string]$entry.id]
        $state = if ($packProperty) { [string](Get-KntJsonProperty $packProperty.Value "state") } else { "DEFAULT" }
        if ($state -eq "DEFAULT") {
            $kind = if ([string]$entry.kind -eq "surface") { "Surface" } else { "Tool" }
            $materializationPlans[[string]$entry.id] = @(Get-DefaultImplementationPlan -DefaultId ([string]$entry.id) -ProjectRoot $projectRoot -Kind $kind -ExistingState $packProperty.Value)
            [void](Apply-DefaultImplementationPlan -Plan $materializationPlans[[string]$entry.id] -ConflictingDefaults $conflictingDefaults)
        }
    }

    foreach ($disabled in @($disabledEntries.ToArray())) {
        $defaultId = [string]$disabled.entry.id
        $plan = @($disabledPlans[$defaultId])
        $conflicts = @($plan | Where-Object { [string]$_.status -in @("CONFLICT", "UNTRUSTED") })
        if ($conflicts.Count -gt 0) {
            Write-Knt "$(if ([string]$disabled.entry.kind -eq 'surface') { 'Surface' } else { 'Tool' }) Default '$defaultId' DISABLED cleanup skipped because a materialized file is modified or untrusted"
            continue
        }
        [void](Apply-DefaultImplementationPlan -Plan $plan -ConflictingDefaults $null)
        if (Clear-DefaultProvenance -PackEntry $disabled.property.Value) {
            $changedDefaults = $true
        }
        if (@($plan | Where-Object { [string]$_.status -eq "STALE_UNCHANGED" -and $_.destination -and (Test-Path -LiteralPath $_.destination -PathType Leaf) }).Count -gt 0) {
            $changedDefaults = $true
        }
    }
    foreach ($conflictingDefault in @($conflictingDefaults | Select-Object -Unique)) {
        $defaults.packs.$conflictingDefault.state = "OVERRIDE"
        $changedDefaults = $true
    }

    foreach ($entry in $selectedEntries) {
        $packProperty = $defaults.packs.PSObject.Properties[[string]$entry.id]
        if (-not $packProperty -or [string](Get-KntJsonProperty $packProperty.Value "state") -ne "DEFAULT") { continue }
        Finalize-DefaultImplementation -DefaultId ([string]$entry.id) -Manifest $Manifest -ProjectRoot $projectRoot
        if (Set-DefaultProvenance -PackEntry $packProperty.Value -Plan $materializationPlans[[string]$entry.id]) {
            $changedDefaults = $true
        }
    }

    $changedManifest = $false
    if (-not $Manifest.paths.PSObject.Properties["defaults"]) {
        $Manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue $defaultsRelative -Force
        $changedManifest = $true
    }
    if ($createdDefaults -or $changedDefaults) {
        Write-KntJsonFile -Path $defaultsPath -Value $defaults
        Write-Knt "Updated Default state file: project/$defaultsRelative"
    }
    if ($changedManifest) {
        Write-KntJsonFile -Path $ManifestPath -Value $Manifest
        Write-Knt "Updated Manifest path declaration: paths.defaults"
    }
    if (-not $createdDefaults -and -not $changedDefaults -and -not $changedManifest) {
        Write-Knt "No changes required; existing Default states were preserved."
    }
    return 0
}

function Test-BaseFiles {
    if (-not (Test-Path -LiteralPath $BaseFilesPath -PathType Leaf)) {
        Write-Knt "base-files.json is missing."
        return $false
    }
    $index = Get-KntJson -Path $BaseFilesPath
    $ok = $true
    $currentVersion = (Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $BaseDir "BASE_VERSION")).Trim()
    if ([string]$index.base_version -ne $currentVersion) {
        Write-Host "[base-check] VERSION  index=$($index.base_version) current=$currentVersion" -ForegroundColor Yellow
        $ok = $false
    }
    $protectedPaths = @(Get-BaseProtectedPaths -Root $Root)
    $indexedPaths = @($index.files | ForEach-Object { [string]$_.path })
    foreach ($expectedPath in $protectedPaths) {
        if ($expectedPath -notin $indexedPaths) {
            Write-Host "[base-check] UNINDEXED  $expectedPath" -ForegroundColor Yellow
            $ok = $false
        }
    }
    foreach ($indexedPath in $indexedPaths) {
        if ($indexedPath -notin $protectedPaths) {
            Write-Host "[base-check] ORPHANED  $indexedPath" -ForegroundColor Yellow
            $ok = $false
        }
    }
    foreach ($entry in @($index.files)) {
        $path = Join-Path $Root $entry.path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Write-Host "[base-check] MISSING  $($entry.path)" -ForegroundColor Red
            $ok = $false
            continue
        }
        try {
            [void](Assert-KntSafePath -Root $Root -Candidate $path -Description "Base protected file")
        }
        catch {
            Write-Host "[base-check] UNSAFE  $($entry.path): $($_.Exception.Message)" -ForegroundColor Red
            $ok = $false
            continue
        }
        $hash = Get-BaseFileHash -Path $path
        if ($hash -ne $entry.sha256) {
            Write-Host "[base-check] CHANGED  $($entry.path)" -ForegroundColor Yellow
            $ok = $false
        }
    }
    if ($ok) { Write-Knt "Base files: OK" }
    return $ok
}

function Resolve-Command($Manifest, [string]$Name) {
    $prop = $Manifest.commands.PSObject.Properties[$Name]
    if (-not $prop) { return $null }
    $value = $prop.Value
    if ($value -is [string]) {
        if ([string]::IsNullOrWhiteSpace($value)) { return $null }
        return [pscustomobject]@{ mode = "legacy"; run = $value; cwd = "project" }
    }
    if ($value.PSObject.Properties["exec"]) {
        $exec = [string]$value.exec
        if ([string]::IsNullOrWhiteSpace($exec)) { return $null }
        $args = @()
        if ($value.PSObject.Properties["args"]) {
            $args = @($value.args | ForEach-Object { [string]$_ })
        }
        $forwardArgs = $false
        if ($value.PSObject.Properties["forward_args"]) {
            $forwardArgs = [bool]$value.forward_args
        }
        $cwd = if ($value.PSObject.Properties["cwd"] -and $value.cwd) { [string]$value.cwd } else { "project" }
        return [pscustomobject]@{
            mode = "structured"
            exec = $exec
            args = $args
            cwd = $cwd
            forward_args = $forwardArgs
        }
    }
    if (-not $value.run) { return $null }
    $cwd = if ($value.cwd) { [string]$value.cwd } else { "project" }
    return [pscustomobject]@{ mode = "legacy"; run = [string]$value.run; cwd = $cwd }
}

function Get-ManifestPathValue($Manifest, [string]$Name, [string]$Default) {
    $value = Get-KntJsonProperty $Manifest.paths $Name
    if ([string]::IsNullOrWhiteSpace([string]$value)) { return $Default }
    return [string]$value
}

function Invoke-ProjectCommand($Manifest, [string]$Name) {
    $spec = Resolve-Command $Manifest $Name
    if (-not $spec) {
        Write-Knt "Command '$Name' is not configured for this project."
        return 0
    }
    try {
        $cwd = Resolve-KntCommandWorkingDirectory -RelativePath ([string]$spec.cwd) -CommandName $Name
    }
    catch {
        Write-Host "[command] $($_.Exception.Message)" -ForegroundColor Red
        return 1
    }
    if (-not (Test-Path -LiteralPath $cwd -PathType Container)) {
        Write-Host "[doctor] MISSING command cwd: $($spec.cwd)" -ForegroundColor Red
        return 1
    }
    Push-Location $cwd
    try {
        $commandOutput = @()
        $commandExitCode = 0
        $commandErrorActionPreference = $ErrorActionPreference
        try {
            # Windows PowerShell 5.1 can surface native stderr merged by 2>&1
            # as NativeCommandError even when the native process exits 0.
            # Keep native process exit semantics separate from PowerShell
            # ErrorRecord semantics so stderr diagnostics do not become
            # failures and PowerShell errors do not become false successes.
            $ErrorActionPreference = "Continue"
            # Reset the process-wide automatic variable without creating a
            # function-local LASTEXITCODE that would shadow native updates.
            $global:LASTEXITCODE = $null
            if ($spec.mode -eq "structured") {
                $forwardedArgs = @($RemainingArgs | Where-Object { $null -ne $_ })
                if ($forwardedArgs.Count -gt 0 -and -not $spec.forward_args) {
                    throw "Structured command '$Name' must set forward_args=true to accept forwarded arguments"
                }
                $invokeArgs = @($spec.args)
                if ($spec.forward_args) { $invokeArgs += $forwardedArgs }
                Write-Knt "$Name -> $($spec.exec)"

                $resolvedCommand = Get-Command -Name $spec.exec -ErrorAction Stop | Select-Object -First 1
                while ($resolvedCommand.CommandType -eq [System.Management.Automation.CommandTypes]::Alias) {
                    $resolvedCommand = $resolvedCommand.ResolvedCommand
                }
                $isNativeCommand = $resolvedCommand.CommandType -eq [System.Management.Automation.CommandTypes]::Application
                $errorCountBefore = $Error.Count
                $commandOutput = @(& $spec.exec @invokeArgs 2>&1)
                $powerShellSucceeded = $?
                $nativeExitCode = $LASTEXITCODE
                $newErrorCount = [Math]::Max(0, $Error.Count - $errorCountBefore)

                if ($isNativeCommand) {
                    $commandExitCode = if ($null -ne $nativeExitCode) { [int]$nativeExitCode } elseif ($powerShellSucceeded) { 0 } else { 1 }
                }
                else {
                    $commandExitCode = if ($powerShellSucceeded -and $newErrorCount -eq 0) { 0 } else { 1 }
                }
            }
            else {
                $forwardedArgs = @($RemainingArgs | Where-Object { $null -ne $_ })
                if ($forwardedArgs.Count -gt 0) {
                    throw "Legacy command '$Name' cannot safely forward arguments; use structured exec/args with forward_args=true"
                }
                Write-Knt "$Name -> $($spec.run)"
                # Capture the legacy expression's terminal status inside the evaluated
                # scope before caller-side output capture can overwrite `$?`.
                $legacyStatus = [pscustomobject]@{
                    PowerShellSucceeded = $null
                    NativeExitCode = $null
                }
                $legacyStatusScript = [string]$spec.run + [Environment]::NewLine +
                    '$legacyStatus.PowerShellSucceeded = $?' + [Environment]::NewLine +
                    '$legacyStatus.NativeExitCode = $LASTEXITCODE'
                $commandOutput = @(Invoke-Expression $legacyStatusScript 2>&1)
                $powerShellSucceeded = ($legacyStatus.PowerShellSucceeded -eq $true)
                $nativeExitCode = $legacyStatus.NativeExitCode

                # `$Error` also records intentionally handled errors such as
                # -ErrorAction SilentlyContinue. Only ErrorRecords that actually reached
                # the merged error stream are unhandled command errors here.
                $emittedErrors = @($commandOutput | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] })
                $nonNativeErrors = @($emittedErrors | Where-Object { [string]$_.FullyQualifiedErrorId -notlike 'NativeCommandError*' })

                if ($nonNativeErrors.Count -gt 0) {
                    $commandExitCode = 1
                }
                elseif ($powerShellSucceeded) {
                    # A successful final PowerShell operation must not inherit
                    # a stale LASTEXITCODE from an earlier native process.
                    $commandExitCode = 0
                }
                elseif ($null -ne $nativeExitCode -and [int]$nativeExitCode -ne 0) {
                    $commandExitCode = [int]$nativeExitCode
                }
                elseif ($emittedErrors.Count -gt 0 -and $nonNativeErrors.Count -eq 0) {
                    # Windows PowerShell 5.1 native stderr with exit 0.
                    $commandExitCode = 0
                }
                else {
                    $commandExitCode = 1
                }
            }
        }
        finally {
            $ErrorActionPreference = $commandErrorActionPreference
        }
        foreach ($outputLine in $commandOutput) { Write-Host $outputLine }
        return $commandExitCode
    }
    finally {
        Pop-Location
    }
}

function Invoke-Verify($Manifest) {
    if (Test-ProjectDefaultEnabled -Manifest $Manifest -DefaultId "generated-integrity") {
        $integrityCode = Invoke-GeneratedIntegrityCheck
        if ($integrityCode -ne 0) { return $integrityCode }
    }
    if (Test-ProjectDefaultEnabled -Manifest $Manifest -DefaultId "pwa") {
        $pwaCode = Invoke-PwaCheck
        if ($pwaCode -ne 0) { return $pwaCode }
    }

    $direct = Resolve-Command $Manifest "verify"
    if ($direct) { return (Invoke-ProjectCommand $Manifest "verify") }
    foreach ($fallback in @("test", "build")) {
        if (Resolve-Command $Manifest $fallback) {
            $code = Invoke-ProjectCommand $Manifest $fallback
            if ($code -ne 0) { return $code }
        }
    }
    return 0
}

function Add-DoctorSchemaErrors {
    param([System.Collections.Generic.List[string]]$Errors, $Data, $Schema, [string]$Path)
    foreach ($errorText in @(Test-KntSchema -Data $Data -Schema $Schema -Path $Path)) {
        [void]$Errors.Add($errorText)
    }
}

function Test-SelectedDefaultImplementations($DefaultsData) {
    $ok = $true
    if (-not $DefaultsData) { return $true }
    $projectRoot = Join-Path $Root "project"
    $catalog = Get-DefaultCatalog
    foreach ($packProperty in @($DefaultsData.packs.PSObject.Properties)) {
        $defaultId = [string]$packProperty.Name
        $state = [string](Get-KntJsonProperty $packProperty.Value "state")
        if ($state -eq "DISABLED") {
            $disabledPlan = @(Get-DefaultRemovalPlan -DefaultId $defaultId -ExistingState $packProperty.Value -Kind "Default")
            foreach ($item in $disabledPlan) {
                if ([string]$item.status -in @("CONFLICT", "UNTRUSTED")) {
                    $reason = if ([string]$item.status -eq "UNTRUSTED") { "untrusted provenance path" } else { "modified" }
                    Write-Host "[doctor] DISABLED Default implementation remains ${reason}: $($item.repository_relative); mark the pack OVERRIDE or delete the file explicitly" -ForegroundColor Red
                    $ok = $false
                }
                elseif ([string]$item.status -eq "STALE_UNCHANGED" -and $item.destination -and (Test-Path -LiteralPath $item.destination -PathType Leaf)) {
                    Write-Host "[doctor] WARNING DISABLED Default '$defaultId' still has a materialized file: $($item.repository_relative); run knt migrate --apply to remove it" -ForegroundColor Yellow
                }
            }
            continue
        }
        if ($state -ne "DEFAULT") { continue }

        $templateRoot = Join-Path $BaseDir ("templates/defaults/" + $defaultId)
        if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
            # Profile-only Defaults intentionally have no materialized files.
            continue
        }

        $plan = @(Get-DefaultImplementationPlan -DefaultId $defaultId -ProjectRoot $projectRoot -Kind "Default" -ExistingState $packProperty.Value)
        foreach ($item in $plan) {
            if ($null -eq $item.template) { continue }
            if (-not (Test-Path -LiteralPath $item.destination -PathType Leaf)) {
                Write-Host "[doctor] MISSING implementation for Default '$defaultId': $($item.repository_relative)" -ForegroundColor Red
                $ok = $false
            }
        }

        $provenanceProperty = $packProperty.Value.PSObject.Properties["materialized_files"]
        $hasProvenance = $null -ne $provenanceProperty -and @($packProperty.Value.materialized_files).Count -gt 0
        if (-not $hasProvenance) {
            Write-Host "[doctor] WARNING Default '$defaultId': legacy DEFAULT provenance unknown; preserve files or mark OVERRIDE before updating" -ForegroundColor Yellow
            continue
        }

        foreach ($recorded in @($packProperty.Value.materialized_files)) {
            $recordedPath = [string]$recorded.path
            $trustedOwnedPaths = Get-DefaultTrustedOwnedPaths -Catalog $catalog -DefaultId $defaultId
            if (-not $trustedOwnedPaths.ContainsKey((Get-KntRepositoryPathKey $recordedPath))) {
                Write-Host "[doctor] DEFAULT '$defaultId' has untrusted provenance path '$recordedPath'; mark the pack OVERRIDE" -ForegroundColor Red
                $ok = $false
                continue
            }
            try {
                $recordedAbsolute = Resolve-KntContainedPath -BaseRoot $Root -RelativePath $recordedPath -Description "Default '$defaultId' provenance path" -AllowRoot
            }
            catch {
                Write-Host "[doctor] DEFAULT '$defaultId' has invalid provenance path '$recordedPath': $($_.Exception.Message)" -ForegroundColor Red
                $ok = $false
                continue
            }
            if (-not (Test-Path -LiteralPath $recordedAbsolute -PathType Leaf)) {
                Write-Host "[doctor] DEFAULT implementation was modified: $recordedPath is missing; restore the Default implementation or mark the pack OVERRIDE" -ForegroundColor Red
                $ok = $false
                continue
            }
            $currentHash = Get-BaseFileHash -Path $recordedAbsolute
            if ($currentHash -ne [string]$recorded.sha256) {
                Write-Host "[doctor] DEFAULT implementation was modified: $recordedPath; restore the Default implementation or mark the pack OVERRIDE" -ForegroundColor Red
                $ok = $false
            }
        }
    }
    return $ok
}

function Invoke-Doctor($Manifest) {
    $ok = $true
    Write-Knt "Repository root: $Root"
    Write-Knt "Project: $($Manifest.project.name) [$($Manifest.project.type)]"
    $selectedProfiles = @([string]$Manifest.profile)
    $profilesProperty = $Manifest.PSObject.Properties["profiles"]
    if ($profilesProperty -and @($Manifest.profiles).Count -gt 0) {
        $selectedProfiles = @($Manifest.profiles | ForEach-Object { [string]$_ })
    }
    Write-Knt "Profile: $($Manifest.profile)$(if ($selectedProfiles.Count -gt 1) { ' [' + ($selectedProfiles -join ', ') + ']' } else { '' })"
    $baseVersion = (Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $BaseDir "BASE_VERSION")).Trim()
    Write-Knt "Base version: $baseVersion"

    if (-not $RootOverride -and -not (Test-BaseFiles)) { $ok = $false }

    $required = @(
        "project/docs/INDEX.md",
        "project/docs/CURRENT_STATE.md",
        "project/contracts/actions.json",
        "project/contracts/surfaces.json"
    )
    foreach ($requiredPath in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $requiredPath) -PathType Leaf)) {
            Write-Host "[doctor] MISSING $requiredPath" -ForegroundColor Red
            $ok = $false
        }
    }

    $schemaErrors = New-Object System.Collections.Generic.List[string]
    $manifestSchema = Get-KntJson -Path (Join-Path $BaseDir "schemas/project.schema.json")
    $actionSchema = Get-KntJson -Path (Join-Path $BaseDir "schemas/action.schema.json")
    $surfaceSchema = Get-KntJson -Path (Join-Path $BaseDir "schemas/surface.schema.json")
    $defaultsSchema = Get-KntJson -Path (Join-Path $BaseDir "schemas/defaults.schema.json")
    $catalog = Get-DefaultCatalog
    Add-DoctorSchemaErrors $schemaErrors $Manifest $manifestSchema "project/project.json"

    $projectRoot = Join-Path $Root "project"
    $actionRelative = Get-ManifestPathValue $Manifest "actions" "contracts/actions.json"
    $surfaceRelative = Get-ManifestPathValue $Manifest "surfaces" "contracts/surfaces.json"
    $actionPath = $null
    $surfacePath = $null
    try { $actionPath = Resolve-KntManifestProjectPath -Manifest $Manifest -Name "actions" -Default "contracts/actions.json" }
    catch { [void]$schemaErrors.Add($_.Exception.Message) }
    try { $surfacePath = Resolve-KntManifestProjectPath -Manifest $Manifest -Name "surfaces" -Default "contracts/surfaces.json" }
    catch { [void]$schemaErrors.Add($_.Exception.Message) }
    if ($actionPath -and (Test-Path -LiteralPath $actionPath -PathType Leaf)) {
        Add-DoctorSchemaErrors $schemaErrors (Get-KntJson -Path $actionPath) $actionSchema $actionRelative
    }
    if ($surfacePath -and (Test-Path -LiteralPath $surfacePath -PathType Leaf)) {
        Add-DoctorSchemaErrors $schemaErrors (Get-KntJson -Path $surfacePath) $surfaceSchema $surfaceRelative
    }
    $defaultsRelative = Get-ManifestPathValue $Manifest "defaults" ""
    $defaultsDataForImplementation = $null
    if (-not [string]::IsNullOrWhiteSpace($defaultsRelative)) {
        $defaultsPath = $null
        try { $defaultsPath = Resolve-KntManifestProjectPath -Manifest $Manifest -Name "defaults" -Default "defaults.json" }
        catch { [void]$schemaErrors.Add($_.Exception.Message) }
        if ($defaultsPath -and (Test-Path -LiteralPath $defaultsPath -PathType Leaf)) {
            $defaultsData = Get-KntJson -Path $defaultsPath
            $defaultsDataForImplementation = $defaultsData
            Add-DoctorSchemaErrors $schemaErrors $defaultsData $defaultsSchema $defaultsRelative
            foreach ($packProperty in @($defaultsData.packs.PSObject.Properties)) {
                try {
                    [void](Find-AnyDefaultCatalogEntry -Catalog $catalog -Identifier ([string]$packProperty.Name))
                }
                catch {
                    [void]$schemaErrors.Add("$defaultsRelative.packs.$($packProperty.Name) references an unknown Default catalog id")
                }
            }
        }
    }

    $catalogErrors = @(Test-KntSchema -Data $catalog -Schema (Get-KntJson -Path (Join-Path $BaseDir "schemas/default-catalog.schema.json")) -Path ".kinotch/defaults/catalog.json")
    foreach ($catalogError in $catalogErrors) { [void]$schemaErrors.Add($catalogError) }

    if ($schemaErrors.Count -gt 0) {
        Write-Host "[doctor] Schema validation failed" -ForegroundColor Red
        foreach ($errorText in $schemaErrors) {
            Write-Host "[doctor] $errorText" -ForegroundColor Red
        }
        $ok = $false
    }
    if (-not (Test-SelectedDefaultImplementations -DefaultsData $defaultsDataForImplementation)) { $ok = $false }
    if ($defaultsDataForImplementation) {
        $manifestSurfaces = @(Get-ManifestSurfaceIds -Manifest $Manifest)
        $manifestProfileIds = if ($Manifest.PSObject.Properties["profiles"] -and @($Manifest.profiles).Count -gt 0) {
            @($Manifest.profiles | ForEach-Object { [string]$_ })
        }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$Manifest.profile)) {
            @([string]$Manifest.profile)
        }
        else { @() }
        $manifestCompatibilityKeys = @(Get-DefaultCompatibilityKeys -Catalog $catalog -ProfileIds $manifestProfileIds -SurfaceIds $manifestSurfaces)
        foreach ($packProperty in @($defaultsDataForImplementation.packs.PSObject.Properties)) {
            $state = [string](Get-KntJsonProperty $packProperty.Value "state")
            if ($state -ne "DEFAULT") { continue }
            try {
                $entry = Find-AnyDefaultCatalogEntry -Catalog $catalog -Identifier ([string]$packProperty.Name)
                $compatibilityError = if ([string]$entry.kind -eq "surface") {
                    $requiredSurfaces = @($entry.compatible_surfaces)
                    if ($requiredSurfaces.Count -gt 0 -and @($requiredSurfaces | Where-Object { $_ -in $manifestSurfaces }).Count -eq 0) {
                        "Surface Default '$($entry.id)' is not enabled in Manifest"
                    }
                    else { $null }
                }
                else {
                    Get-DefaultCompatibilityError -Entry $entry -SelectedSurfaces $manifestCompatibilityKeys
                }
                if ($compatibilityError) {
                    Write-Host "[doctor] $compatibilityError" -ForegroundColor Red
                    $ok = $false
                }
            }
            catch {
                # Unknown catalog IDs are already reported as schema errors above.
            }
        }
    }

    $profiles = New-Object System.Collections.Generic.List[object]
    foreach ($selectedProfile in $selectedProfiles) {
        $profileFileName = $selectedProfile
        try {
            $profileEntry = Find-DefaultCatalogEntry -Catalog $catalog -Identifier $selectedProfile -Kind "surface"
            $profileFileName = Get-DefaultProfileName $profileEntry
        }
        catch {
            # Existing custom profile names remain diagnosable by their profile file.
        }
        $profilePath = Join-Path $BaseDir ("profiles/" + $profileFileName + ".json")
        if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
            Write-Host "[doctor] MISSING profile: $selectedProfile" -ForegroundColor Red
            $ok = $false
        }
        else {
            [void]$profiles.Add((Get-KntJson -Path $profilePath))
        }
    }

    $modules = @($Manifest.runtime.modules)
    Write-Knt ("Runtime modules: " + ($(if ($modules.Count) { $modules -join ", " } else { "(none)" })))
    $enabled = @($Manifest.surfaces.PSObject.Properties | Where-Object { $_.Value -eq $true } | ForEach-Object { $_.Name })
    Write-Knt ("Surfaces: " + ($(if ($enabled.Count) { $enabled -join ", " } else { "(none)" })))

    if ($profiles.Count -gt 0) {
        $recommendedSurfaces = @($profiles | ForEach-Object {
            $profileSurfaces = Get-KntJsonProperty $_ "surfaces"
            @($profileSurfaces.PSObject.Properties | Where-Object { $_.Value -eq $true } | ForEach-Object { $_.Name })
        } | Select-Object -Unique)
        foreach ($profileSurface in $recommendedSurfaces) {
            $manifestValue = Get-KntJsonProperty $Manifest.surfaces $profileSurface
            if ($manifestValue -ne $true) {
                Write-Host "[doctor] CONTRADICTION profile surface '$profileSurface' is not enabled in manifest." -ForegroundColor Red
                $ok = $false
            }
        }
        foreach ($manifestSurface in @($Manifest.surfaces.PSObject.Properties | Where-Object { $_.Value -eq $true })) {
            if ($manifestSurface.Name -notin $recommendedSurfaces) {
                Write-Host "[doctor] WARN manifest surface '$($manifestSurface.Name)' is not recommended by selected profile(s)." -ForegroundColor Yellow
            }
        }
    }

    foreach ($pathProperty in @($Manifest.paths.PSObject.Properties)) {
        if ([string]::IsNullOrWhiteSpace([string]$pathProperty.Value)) { continue }
        try {
            $candidate = Resolve-KntManifestProjectPath -Manifest $Manifest -Name ([string]$pathProperty.Name) -Default ([string]$pathProperty.Value)
            if (-not (Test-Path -LiteralPath $candidate)) {
                Write-Host "[doctor] MISSING path: $($pathProperty.Value) ($($pathProperty.Name))" -ForegroundColor Red
                $ok = $false
            }
        }
        catch {
            Write-Host "[doctor] $($_.Exception.Message)" -ForegroundColor Red
            $ok = $false
        }
    }

    foreach ($commandProperty in @($Manifest.commands.PSObject.Properties)) {
        $spec = Resolve-Command $Manifest $commandProperty.Name
        if ($spec) {
            try {
                $cwd = Resolve-KntCommandWorkingDirectory -RelativePath ([string]$spec.cwd) -CommandName ([string]$commandProperty.Name)
                if (-not (Test-Path -LiteralPath $cwd -PathType Container)) {
                    Write-Host "[doctor] MISSING command cwd: $($spec.cwd) ($($commandProperty.Name))" -ForegroundColor Red
                    $ok = $false
                }
            }
            catch {
                Write-Host "[doctor] $($_.Exception.Message)" -ForegroundColor Red
                $ok = $false
            }
        }
    }

    $configured = @($Manifest.commands.PSObject.Properties | Where-Object { $null -ne (Resolve-Command $Manifest $_.Name) } | ForEach-Object { $_.Name })
    Write-Knt ("Commands: " + ($(if ($configured.Count) { $configured -join ", " } else { "(none configured yet)" })))

    if ($ok) {
        Write-Host "[doctor] OK" -ForegroundColor Green
        return 0
    }
    Write-Host "[doctor] FAILED" -ForegroundColor Red
    return 1
}

function Show-Help {
    @"
KiNoTch. repository command router

Usage:
  knt.cmd <command>
  .kinotch/scripts/knt.ps1 <command>

Common commands:
  doctor      Base/project structure and schema diagnostics
  init        Create a Project from catalog Surface/Tool Defaults
              --profile minimal|web-app|cli|windows-gui|mcp|api|agent|library
              --default ci-test|generated-integrity|file-io|pwa|config|logging
  migrate     Show or explicitly record catalog Default candidates
  base-check  Detect modifications in common Base files
  base-refresh Regenerate Base file hashes (repository-base only)
  setup       Project setup command
  dev         Project development command
  test        Project tests
  build       Project build
  verify      L1 Project verify command; falls back to test + build
  generated-integrity  Check selected generated artifacts against SHA-256 metadata
  pwa-check   Check selected PWA manifest, service worker, and registration helper
  smoke       Project smoke / real-entry check
  help        This help
"@ | Write-Host
}

try {
    if ($Command -eq "help" -or $Command -eq "--help" -or $Command -eq "-h") {
        Show-Help
        exit 0
    }
    if ($Command -eq "base-check") {
        if (Test-BaseFiles) { exit 0 } else { exit 1 }
    }
    if ($Command -eq "base-refresh") {
        Assert-RepositoryWriteAllowed "base-refresh"
        $refreshManifest = Get-Manifest
        if ($refreshManifest.project.type -ne "repository-base") {
            throw "base-refresh is only available for project.type repository-base"
        }
        Update-BaseIndex -Root $Root
        Write-Knt "Base index refreshed"
        exit 0
    }
    if ($Command -eq "init") {
        exit (Invoke-Init)
    }

    if ($Command -eq "migrate") {
        $migrationManifest = if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) { Get-Manifest } else { $null }
        exit (Invoke-Migrate $migrationManifest)
    }

    $manifest = Get-Manifest
    if ($Command -eq "doctor") { exit (Invoke-Doctor $manifest) }
    if ($Command -eq "generated-integrity") { exit (Invoke-GeneratedIntegrityCheck) }
    if ($Command -eq "pwa-check") { exit (Invoke-PwaCheck) }

    if ($Command -eq "verify") {
        exit (Invoke-Verify $manifest)
    }

    if ($Command -in @("setup","dev","test","build","smoke","deploy")) {
        exit (Invoke-ProjectCommand $manifest $Command)
    }

    Write-Host "Unknown command: $Command" -ForegroundColor Red
    Show-Help
    exit 2
}
catch {
    Write-Host "[knt] ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}
