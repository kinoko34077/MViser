# Native commands intentionally exercise stdout/stderr boundaries in several
# tests. Continue allows Windows PowerShell 5.1 to collect native stderr as
# data; assertions and explicit throws still fail the corresponding test.
$ErrorActionPreference = "Continue"

$TestDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestDir)
$FixtureRoot = Join-Path $RepoRoot ".kinotch/tests/fixtures"
$PowerShellExecutable = $null
if ($PSVersionTable.PSEdition -eq "Desktop") {
    $PowerShellExecutable = (Get-Command powershell -ErrorAction Stop | Select-Object -First 1).Source
} else {
    $PowerShellExecutable = (Get-Command pwsh -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ([string]::IsNullOrWhiteSpace($PowerShellExecutable)) {
        $PowerShellExecutable = (Get-Command powershell -ErrorAction Stop | Select-Object -First 1).Source
    }
}
. (Join-Path $RepoRoot ".kinotch/scripts/update-base-index.ps1")
. (Join-Path $RepoRoot ".kinotch/scripts/knt-validation.ps1")
$Passed = 0
$Failed = 0
$Skipped = 0

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Assert-Equal($Expected, $Actual, [string]$Message) {
    if ($Expected -ne $Actual) {
        throw "$Message expected=[$Expected] actual=[$Actual]"
    }
}

function Get-SchemaKeywordNames {
    param($Schema)

    $names = New-Object System.Collections.Generic.List[string]
    if ((Get-KntJsonType $Schema) -ne "object") { return @() }
    foreach ($property in $Schema.PSObject.Properties) {
        [void]$names.Add([string]$property.Name)
        switch ([string]$property.Name) {
            "properties" {
                foreach ($child in @($property.Value.PSObject.Properties)) {
                    foreach ($name in @(Get-SchemaKeywordNames $child.Value)) { [void]$names.Add($name) }
                }
            }
            "additionalProperties" {
                if ((Get-KntJsonType $property.Value) -eq "object") {
                    foreach ($name in @(Get-SchemaKeywordNames $property.Value)) { [void]$names.Add($name) }
                }
            }
            "oneOf" {
                foreach ($candidate in @($property.Value)) {
                    foreach ($name in @(Get-SchemaKeywordNames $candidate)) { [void]$names.Add($name) }
                }
            }
            "items" {
                foreach ($name in @(Get-SchemaKeywordNames $property.Value)) { [void]$names.Add($name) }
            }
        }
    }
    return @($names | Select-Object -Unique)
}

function Get-FixtureProtectedPaths([string]$Root) {
    $fixed = @(
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".github/workflows/verify.yml",
        "AGENTS.md",
        "knt.cmd"
    )
    $common = @(Get-ChildItem -LiteralPath (Join-Path $Root ".kinotch") -Recurse -File -Force | ForEach-Object {
        $relative = ConvertTo-BaseRelativePath -Root $Root -AbsolutePath $_.FullName
        if ($relative -ne ".kinotch/base-files.json") { $relative }
    })
    return @($fixed + $common | Sort-Object)
}

function Set-FixtureBaseIndex([string]$Root) {
    $entries = @(Get-FixtureProtectedPaths $Root | ForEach-Object {
        [pscustomobject]@{
            path = $_
            sha256 = Get-BaseFileHash -Path (Join-Path $Root $_)
        }
    })
    $index = [pscustomobject]@{
        schema_version = 1
        base_version = (Get-Content -Raw -LiteralPath (Join-Path $Root ".kinotch/BASE_VERSION")).Trim()
        files = $entries
    }
    $json = ConvertTo-Json $index -Depth 10
    [IO.File]::WriteAllText((Join-Path $Root ".kinotch/base-files.json"), $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}

function Set-FixtureAsBase([string]$Root) {
    $manifestPath = Join-Path $Root "project/project.json"
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    $manifest.project.type = "repository-base"
    [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-KntFixture {
    param(
        [string]$Name,
        [string]$Command,
        [int]$ExpectedExit = 0,
        [scriptblock]$AssertOutput,
        [scriptblock]$Prepare,
        [string[]]$Arguments
    )
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("kinotch-base-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        Get-ChildItem -Force $RepoRoot | Where-Object {
            $_.Name -notin @(".git", ".superpowers")
        } | Copy-Item -Destination $tempRoot -Recurse -Force
        Remove-Item -LiteralPath (Join-Path $tempRoot "project") -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $FixtureRoot $Name) -Destination (Join-Path $tempRoot "project") -Recurse -Force
        if ($Prepare) { & $Prepare $tempRoot }
        if ($script:SkipCurrentTest) { return }
        $router = Join-Path $tempRoot ".kinotch/scripts/knt.ps1"
        $invokeArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $router, "-RootOverride", $tempRoot, $Command) + @($Arguments)
        $outputLines = @(& $PowerShellExecutable @invokeArgs 2>&1)
        $exitCode = $LASTEXITCODE
        $output = $outputLines -join [Environment]::NewLine
        Assert-Equal $ExpectedExit $exitCode "$Name $Command exit code"
        if ($AssertOutput) { & $AssertOutput $tempRoot $output }
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-KntInitFixture {
    param(
        [string[]]$Profiles,
        [string[]]$Defaults,
        [int]$ExpectedExit = 0,
        [switch]$RemoveExistingCi,
        [scriptblock]$Prepare,
        [scriptblock]$AssertOutput
    )
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("kinotch-init-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        Get-ChildItem -Force $RepoRoot | Where-Object {
            $_.Name -notin @(".git", ".superpowers")
        } | Copy-Item -Destination $tempRoot -Recurse -Force
        Remove-Item -LiteralPath (Join-Path $tempRoot "project") -Recurse -Force
        if ($RemoveExistingCi) {
            Remove-Item -LiteralPath (Join-Path $tempRoot ".github/workflows/verify.yml") -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath (Join-Path $tempRoot ".github/workflows/kinotch-default.yml") -Force -ErrorAction SilentlyContinue
        }
        if ($Prepare) { & $Prepare $tempRoot }
        if ($script:SkipCurrentTest) { return }
        $router = Join-Path $tempRoot ".kinotch/scripts/knt.ps1"
        $invokeArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $router, "-RootOverride", $tempRoot, "init")
        foreach ($profile in $Profiles) { $invokeArgs += @("--profile", $profile) }
        if ($Defaults) {
            foreach ($default in $Defaults) { $invokeArgs += @("--default", $default) }
        }
        $initOutput = @(& $PowerShellExecutable @invokeArgs 2>&1)
        $initExit = $LASTEXITCODE
        Assert-Equal $ExpectedExit $initExit "init exit code"
        if ($ExpectedExit -ne 0) {
            if ($AssertOutput) { & $AssertOutput $tempRoot ($initOutput -join [Environment]::NewLine) }
            return
        }

        $doctorOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $tempRoot doctor 2>&1)
        $doctorExit = $LASTEXITCODE
        Assert-Equal 0 $doctorExit "generated project doctor exit code"
        if ($AssertOutput) { & $AssertOutput $tempRoot (($initOutput + $doctorOutput) -join [Environment]::NewLine) }
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-KntShapeMigrateFixture {
    param(
        [scriptblock]$AssertOutput,
        [string]$WorkflowText = "name: Verify`nrun: npm test",
        [string]$IncidentalWorkflowText = "",
        [string]$PackageJson = '{"scripts":{"test":"node --test","build":"vite build"},"devDependencies":{"vite":"latest"}}',
        [switch]$GeneratedFile,
        [switch]$IntegrityEvidence,
        [switch]$UseBaseWorkflow,
        [switch]$VendorIntegrityEvidence,
        [switch]$NoWebAssets,
        [switch]$AgentRoot
    )
    $tempPrefix = if ($AgentRoot) { "kinotch-agent-shape-test-" } else { "kinotch-shape-test-" }
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ($tempPrefix + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        Get-ChildItem -Force $RepoRoot | Where-Object {
            $_.Name -notin @(".git", ".superpowers", "project")
        } | Copy-Item -Destination $tempRoot -Recurse -Force
        $workflowRoot = Join-Path $tempRoot ".github/workflows"
        New-Item -ItemType Directory -Path $workflowRoot -Force | Out-Null
        if (-not [string]::IsNullOrWhiteSpace($IncidentalWorkflowText)) {
            Set-Content -LiteralPath (Join-Path $workflowRoot "incidental-maintenance.yml") -Value $IncidentalWorkflowText -NoNewline
        }
        $baseWorkflowText = $null
        if ($UseBaseWorkflow) {
            $baseWorkflowText = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".github/workflows/verify.yml")
        }
        Remove-Item -LiteralPath $workflowRoot -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $workflowRoot -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $tempRoot "package.json") -Value $PackageJson -NoNewline
        if ($UseBaseWorkflow) {
            [IO.File]::WriteAllText((Join-Path $workflowRoot "verify.yml"), $baseWorkflowText, (New-Object System.Text.UTF8Encoding($false)))
        }
        else {
            Set-Content -LiteralPath (Join-Path $workflowRoot "verify.yml") -Value $WorkflowText -NoNewline
        }
        if (-not $NoWebAssets) {
            New-Item -ItemType Directory -Path (Join-Path $tempRoot "public") -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $tempRoot "public/manifest.json") -Value '{"name":"Shape","start_url":"/"}' -NoNewline
            Set-Content -LiteralPath (Join-Path $tempRoot "service-worker.js") -Value "self.addEventListener('fetch', () => {});" -NoNewline
        }
        if ($GeneratedFile) {
            New-Item -ItemType Directory -Path (Join-Path $tempRoot "src") -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $tempRoot "src/generated-output.js") -Value "export default 'generated';" -NoNewline
        }
        if ($IntegrityEvidence) {
            New-Item -ItemType Directory -Path (Join-Path $tempRoot "scripts") -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $tempRoot "scripts/integrity-check.ps1") -Value "Get-FileHash -Algorithm SHA256; stale check" -NoNewline
        }
        if ($VendorIntegrityEvidence) {
            New-Item -ItemType Directory -Path (Join-Path $tempRoot "public/pdfjs/src/core") -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $tempRoot "public/pdfjs/src/core/calculate_sha256.js") -Value "function calculateSHA256() {}; stale reference" -NoNewline
        }
        $router = Join-Path $tempRoot ".kinotch/scripts/knt.ps1"
        $baseSource = Join-Path $RepoRoot ".kinotch"
        $invokeArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $router, "-RootOverride", $tempRoot, "-BaseOverride", $baseSource, "migrate")
        $outputLines = @(& $PowerShellExecutable @invokeArgs 2>&1)
        $exitCode = $LASTEXITCODE
        Assert-Equal 0 $exitCode "shape migrate exit code"
        if ($AssertOutput) { & $AssertOutput $tempRoot ($outputLines -join [Environment]::NewLine) }
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-KntExternalBaseFixture {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$FixtureName,
        [int]$ExpectedExit = 0,
        [scriptblock]$Prepare,
        [scriptblock]$AssertOutput
    )
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("kinotch-external-base-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        if ($FixtureName) {
            Copy-Item -LiteralPath (Join-Path $FixtureRoot $FixtureName) -Destination (Join-Path $tempRoot "project") -Recurse -Force
        }
        if ($Prepare) { & $Prepare $tempRoot }
        $router = Join-Path $RepoRoot ".kinotch/scripts/knt.ps1"
        $baseSource = Join-Path $RepoRoot ".kinotch"
        $invokeArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $router,
            "-RootOverride", $tempRoot, "-BaseOverride", $baseSource, $Command
        ) + @($Arguments)
        $outputLines = @(& $PowerShellExecutable @invokeArgs 2>&1)
        $exitCode = $LASTEXITCODE
        $output = $outputLines -join [Environment]::NewLine
        Assert-Equal $ExpectedExit $exitCode "external Base $Command exit code"
        if ($AssertOutput) { & $AssertOutput $tempRoot $output }
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-TestCase([string]$Name, [scriptblock]$Body) {
    $script:SkipCurrentTest = $false
    try {
        & $Body
        if ($script:SkipCurrentTest) {
            $script:Skipped++
            Write-Host "[SKIP] $Name" -ForegroundColor Yellow
        }
        else {
            $script:Passed++
            Write-Host "[PASS] $Name" -ForegroundColor Green
        }
    }
    catch {
        $script:Failed++
        Write-Host "[FAIL] $Name :: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Invoke-TestCase "Windows-style repository path is canonicalized" {
    $actual = ConvertTo-BaseRelativePath -Root "C:\repo" -AbsolutePath "C:\repo\.kinotch\README_BASE.md"
    Assert-Equal ".kinotch/README_BASE.md" $actual "Windows-style relative path"
}

Invoke-TestCase "Unix-style repository path is canonicalized" {
    $actual = ConvertTo-BaseRelativePath -Root "/home/user/repo" -AbsolutePath "/home/user/repo/.kinotch/README_BASE.md"
    Assert-Equal ".kinotch/README_BASE.md" $actual "Unix-style relative path"
}

Invoke-TestCase "Protected paths never begin with a separator" {
    $paths = @(Get-BaseProtectedPaths -Root $RepoRoot)
    Assert-True (@($paths | Where-Object { $_ -match "^[\\/]" }).Count -eq 0) "protected path has a leading separator"
}

Invoke-TestCase "Protected paths include hidden Base files" {
    $paths = @(Get-BaseProtectedPaths -Root $RepoRoot)
    Assert-True ($paths -contains ".kinotch/templates/project/.gitignore") "hidden template file is not protected"
}

Invoke-TestCase "Base file hash is line-ending stable" {
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("kinotch-hash-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $crlfPath = Join-Path $tempRoot "crlf.txt"
        $lfPath = Join-Path $tempRoot "lf.txt"
        [IO.File]::WriteAllText($crlfPath, "alpha`r`nbeta`r`n", $utf8)
        [IO.File]::WriteAllText($lfPath, "alpha`nbeta`n", $utf8)
        Assert-Equal (Get-BaseFileHash $lfPath) (Get-BaseFileHash $crlfPath) "line-ending stable Base hash"
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Invoke-TestCase "Protected paths and Base index use canonical separators" {
    $paths = @(Get-BaseProtectedPaths -Root $RepoRoot)
    Assert-True (@($paths | Where-Object { $_ -match "\\" }).Count -eq 0) "protected path contains a Windows separator"
    $index = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/base-files.json") | ConvertFrom-Json
    $indexedPaths = @($index.files | ForEach-Object { [string]$_.path })
    Assert-True (@($indexedPaths | Where-Object { $_ -match "^[\\/]" }).Count -eq 0) "index path has a leading separator"
    Assert-True (@($indexedPaths | Where-Object { $_ -match "\\" }).Count -eq 0) "index path contains a Windows separator"
    $inventoryEntry = $index.files | Where-Object path -eq ".kinotch/FILE_INVENTORY.txt"
    Assert-Equal (Get-BaseFileHash (Join-Path $RepoRoot ".kinotch/FILE_INVENTORY.txt")) $inventoryEntry.sha256 "index inventory hash"
}

Invoke-TestCase "Project path containment is OS-aware and rejects sibling escapes" {
    $helperPath = Join-Path $RepoRoot ".kinotch/scripts/path-containment.ps1"
    Assert-True (Test-Path -LiteralPath $helperPath -PathType Leaf) "path containment helper is missing"
    . $helperPath
    Assert-True (Test-KntProjectPathContained -Root "C:\repo" -Candidate "C:\repo\file.txt" -Windows $true) "Windows child path was rejected"
    Assert-True (-not (Test-KntProjectPathContained -Root "C:\repo" -Candidate "C:\repo-other\file.txt" -Windows $true)) "Windows sibling prefix was accepted"
    Assert-True (-not (Test-KntProjectPathContained -Root "C:\repo" -Candidate "C:\repo\..\outside.txt" -Windows $true)) "Windows parent escape was accepted"
    Assert-True (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/Repo/file.txt" -Windows $false) "Unix child path was rejected"
    Assert-True (-not (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/repo/file.txt" -Windows $false)) "Unix case-variant sibling was accepted"
    Assert-True (-not (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/Repo-other/file.txt" -Windows $false)) "Unix sibling prefix was accepted"
    Assert-True (-not (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/Repo/../outside.txt" -Windows $false)) "Unix parent escape was accepted"
    Assert-True (-not (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/Repo" -Windows $false)) "Project root was implicitly accepted"
    Assert-True (Test-KntProjectPathContained -Root "/tmp/Repo" -Candidate "/tmp/Repo" -Windows $false -AllowRoot) "Explicit root allowance was rejected"
}

Invoke-TestCase "valid minimal project passes doctor" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 0
}
Invoke-TestCase "Manifest paths reject Project-root escapes" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $outside = Join-Path (Split-Path -Parent $root) ((Split-Path -Leaf $root) + "-outside")
        New-Item -ItemType Directory -Path (Join-Path $outside "docs") -Force | Out-Null
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths.docs = "..\$((Split-Path -Leaf $outside))/docs"
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "outside.*Project|contain|boundary|relative") "Manifest path escape was not rejected"
    }
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $outside = Join-Path (Split-Path -Parent $root) ((Split-Path -Leaf $root) + "-absolute-outside")
        New-Item -ItemType Directory -Path (Join-Path $outside "docs") -Force | Out-Null
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths.docs = Join-Path $outside "docs"
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "outside.*Project|contain|boundary|relative") "Absolute Manifest path was not rejected"
    }
}
Invoke-TestCase "command cwd rejects Repository-root escapes before execution" {
    Invoke-KntFixture -Name "valid-minimal" -Command "test" -ExpectedExit 1 -Prepare {
        param($root)
        $outside = Join-Path (Split-Path -Parent $root) ((Split-Path -Leaf $root) + "-command-outside")
        New-Item -ItemType Directory -Path $outside -Force | Out-Null
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{
            exec = "pwsh"
            args = @("-NoProfile", "-Command", "Write-Output escaped")
            cwd = "..\$((Split-Path -Leaf $outside))"
            forward_args = $false
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "outside.*Repository|contain|boundary|cwd") "Command cwd escape was not rejected"
        Assert-True ($output -notmatch "escaped") "Escaped command was executed"
    }
}
Invoke-TestCase "Base manifest keeps Runtime modules empty" {
    $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot "project/project.json") | ConvertFrom-Json
    Assert-Equal "repository-base" $manifest.project.type "Base project type"
    Assert-Equal 0 @($manifest.runtime.modules).Count "Base Runtime module declaration"
}
Invoke-TestCase "valid command string remains accepted" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 0
}
Invoke-TestCase "valid command object remains accepted" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{ run = "Write-Output valid"; cwd = "." }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    }
}
Invoke-TestCase "valid structured command object remains accepted" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{
            exec = "pwsh"
            args = @("-NoProfile", "-Command", "Write-Output valid")
            cwd = "."
            forward_args = $false
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    }
}
Invoke-TestCase "schema-valued additional command property is validated" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = 123
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "project/project.json.commands.test") "command schema path was not reported"
        Assert-True ($output -match "commands.test has type integer") "command type error was not reported"
    }
}
Invoke-TestCase "schema-valued additional path property is validated" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths.docs = 123
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "project/project.json.paths.docs") "path schema path was not reported"
    }
}
Invoke-TestCase "invalid Default state is rejected by doctor" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{ cli = [pscustomobject]@{ state = "MAYBE" } }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "defaults.*state|state.*DEFAULT") "invalid Default state was not reported"
    }
}
Invoke-TestCase "doctor rejects a selected Default without its implementation" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{ pwa = [pscustomobject]@{ state = "DEFAULT" } }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "MISSING implementation.*pwa") "missing Default implementation was not reported"
    }
}
Invoke-TestCase "init creates a doctor-valid multi-profile Project" {
    Invoke-KntInitFixture -Profiles @("cli", "mcp") -AssertOutput {
        param($root, $output)
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/project.json") | ConvertFrom-Json
        Assert-Equal "cli" $manifest.profile "primary profile"
        Assert-Equal 2 @($manifest.profiles).Count "selected profile count"
        Assert-True (@($manifest.profiles) -contains "mcp") "mcp profile was not recorded"
        Assert-True ($manifest.surfaces.cli -eq $true -and $manifest.surfaces.mcp -eq $true) "selected surfaces were not enabled"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.cli.state "cli Default state"
        Assert-Equal "DEFAULT" $defaults.packs.mcp.state "mcp Default state"
        Assert-True (Test-Path (Join-Path $root "README.md")) "root README was not generated"
        Assert-True (Test-Path (Join-Path $root "project/src/README.md")) "project source placeholder was not generated"
        Assert-True (Test-Path (Join-Path $root "project/tests/README.md")) "project test placeholder was not generated"
    }
}
Invoke-TestCase "Tool Defaults require a compatible selected Surface" {
    Invoke-KntInitFixture -Profiles @("minimal") -Defaults @("ci-test") -RemoveExistingCi -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs."ci-test".state "minimal + ci-test state"
    }
    Invoke-KntInitFixture -Profiles @("minimal") -Defaults @("pwa") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "not compatible|requires.*Surface") "minimal + pwa was accepted"
    }
    Invoke-KntInitFixture -Profiles @("cli") -Defaults @("pwa") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "not compatible|requires.*Surface") "cli + pwa was accepted"
    }
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.pwa.state "web-app + pwa state"
    }
    Invoke-KntInitFixture -Profiles @("windows-gui") -Defaults @("file-io") -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs."file-io".state "windows + file-io state"
    }
}
Invoke-TestCase "init accepts all catalog surface profiles without Runtime injection" {
    Invoke-KntInitFixture -Profiles @("minimal", "web-app", "cli", "windows-gui", "mcp", "api", "agent", "library") -AssertOutput {
        param($root, $output)
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/project.json") | ConvertFrom-Json
        Assert-Equal 8 @($manifest.profiles).Count "all selected profile count"
        Assert-Equal 0 @($manifest.runtime.modules).Count "Runtime modules were injected by profile selection"
        Assert-True ($manifest.profiles -contains "web-app") "web-app profile was not recorded"
        Assert-True ($manifest.surfaces.web -eq $true) "web surface was not enabled"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.PSObject.Properties["web-app"].Value.state "web-app Default state"
        Assert-Equal "DEFAULT" $defaults.packs.windows.state "windows Default state"
    }
}
Invoke-TestCase "surface Defaults materialize safe CLI, Windows, MCP, and API helpers" {
    Invoke-KntInitFixture -Profiles @("cli", "windows-gui", "mcp", "api") -AssertOutput {
        param($root, $output)
        foreach ($relative in @(
            "project/tools/cli-default.ps1",
            "project/tools/windows-shell.ps1",
            "project/contracts/mcp-tools.json",
            "project/contracts/api-error-envelope.json"
        )) {
            Assert-True (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf) "missing surface Default implementation: $relative"
        }
        Assert-True ($output -match "Surface Default 'cli' materialized") "CLI surface Default was not materialized"
        Assert-True ($output -match "Surface Default 'api' materialized") "API surface Default was not materialized"
    }
}
Invoke-TestCase "CLI Surface Kit preserves Project arguments and separates output streams" {
    Invoke-KntInitFixture -Profiles @("cli") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/cli-default.ps1"
        $probe = Join-Path $root "cli-kit-probe.ps1"
        $probeText = @'
param(
    [Parameter(Mandatory=$true)][string]$HelperPath,
    [Parameter(Mandatory=$true)][ValidateSet("parse", "output", "exit")][string]$Mode
)
$ErrorActionPreference = "Stop"
. $HelperPath
switch ($Mode) {
    "parse" {
        $options = Get-CliCommonOptions @("--json", "--quiet", "--verbose", "--dry-run", "--yes", "--domain-value")
        if (-not $options.Json -or -not $options.Quiet -or -not $options.Verbose -or -not $options.DryRun -or -not $options.Yes) { throw "common flags were not parsed" }
        if ($options.RemainingArgs.Count -ne 1 -or $options.RemainingArgs[0] -ne "--domain-value") { throw "Project argument was consumed" }
        $terminated = Get-CliCommonOptions @("--json", "--", "--help", "--domain")
        if (-not $terminated.Json -or $terminated.Help) { throw "CLI option terminator changed Default option parsing" }
        if ($terminated.RemainingArgs.Count -ne 3 -or $terminated.RemainingArgs[0] -ne "--" -or $terminated.RemainingArgs[1] -ne "--help" -or $terminated.RemainingArgs[2] -ne "--domain") { throw "CLI option terminator did not preserve Project arguments" }
        Write-Output "parse-ok"
    }
    "output" {
        Write-CliOutput -Message "normal"
        Write-CliOutput -Message "hidden" -Quiet
        Write-CliDiagnostic -Message "hidden-diagnostic"
        Write-CliDiagnostic -Message "diagnostic" -VerboseOutput
        Write-CliJson -Value ([pscustomobject]@{ kind = "json" })
        Write-CliResult -Value ([pscustomobject]@{ kind = "result" }) -Json
    }
    "exit" {
        Exit-Cli -Code 7
    }
}
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $parseOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper -Mode parse 2>&1)
        Assert-Equal 0 $LASTEXITCODE "CLI common option probe exit code"
        Assert-True (($parseOutput -join "`n") -match "parse-ok") "CLI common option probe did not complete"

        $stderrPath = Join-Path $root "cli-kit.stderr"
        $stdoutOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper -Mode output 2> $stderrPath)
        Assert-Equal 0 $LASTEXITCODE "CLI output probe exit code"
        $stdoutText = $stdoutOutput -join "`n"
        $stderrText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -Raw -Encoding UTF8 $stderrPath } else { "" }
        Assert-True ($stdoutText -match "normal") "CLI stdout helper did not write normal output"
        Assert-True ($stdoutText -notmatch "hidden") "CLI quiet output was not suppressed"
        Assert-True ($stdoutText -match '"kind":"json"') "CLI JSON output was not emitted"
        Assert-True ($stdoutText -match '"kind":"result"') "CLI result JSON was not emitted"
        Assert-True ($stderrText -match "diagnostic") "CLI diagnostic was not written to stderr"
        Assert-True ($stderrText -notmatch "hidden-diagnostic") "CLI non-verbose diagnostic was not suppressed"

        $exitOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper -Mode exit 2>&1)
        Assert-Equal 7 $LASTEXITCODE "CLI exit helper code"
    }
}
Invoke-TestCase "init records selected Tool Defaults from the catalog" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.pwa.state "pwa Default state"
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/project.json") | ConvertFrom-Json
        Assert-Equal 0 @($manifest.runtime.modules).Count "Tool Default injected Runtime modules"
    }
}
Invoke-TestCase "init materializes safe Default implementations" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("ci-test", "pwa", "generated-integrity", "file-io") -RemoveExistingCi -AssertOutput {
        param($root, $output)
        $ciPath = Join-Path $root ".github/workflows/kinotch-default.yml"
        Assert-True (Test-Path $ciPath) "ci-test workflow was not generated"
        Assert-True ((Get-Content -Raw -Encoding UTF8 $ciPath) -match "knt\.ps1 setup") "ci-test workflow has no setup step"
        $pwaManifestPath = Join-Path $root "project/public/manifest.webmanifest"
        Assert-True (Test-Path $pwaManifestPath) "PWA manifest was not generated"
        $pwaManifest = Get-Content -Raw -Encoding UTF8 $pwaManifestPath | ConvertFrom-Json
        Assert-Equal "." $pwaManifest.start_url "PWA manifest must use a relative start_url"
        Assert-True (Test-Path (Join-Path $root "project/public/service-worker.js")) "service worker was not generated"
        Assert-True (Test-Path (Join-Path $root "project/src/pwa/register.js")) "PWA registration helper was not generated"
        Assert-True (Test-Path (Join-Path $root "project/generated-integrity.json")) "generated-integrity config was not generated"
        Assert-True (Test-Path (Join-Path $root "project/tools/check-generated.ps1")) "generated-integrity checker was not generated"
        Assert-True (Test-Path (Join-Path $root "project/tools/update-generated-integrity.ps1")) "generated-integrity updater was not generated"
        $fileIo = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/contracts/file-io.json") | ConvertFrom-Json
        Assert-Equal "UTF-8 text helper only; binary Projects provide their own byte/path callback." $fileIo.helper_scope "file-io helper scope"
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root pwa-check 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "pwa-check exit code"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root generated-integrity 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "generated-integrity exit code"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root verify 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "verify Default integration exit code"
        Set-Content -LiteralPath (Join-Path $root "project/source.txt") -Value "source-v1" -NoNewline
        Set-Content -LiteralPath (Join-Path $root "project/generated.txt") -Value "generated-v1" -NoNewline
        $updater = Join-Path $root "project/tools/update-generated-integrity.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $updater -Source source.txt -Artifact generated.txt -Generator project-owned 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "generated-integrity updater exit code"
        $integrityConfig = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/generated-integrity.json") | ConvertFrom-Json
        Assert-True ($integrityConfig.entries[0].source_sha256 -match "^[0-9a-f]{64}$") "source hash was not recorded"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router generated-integrity 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "generated-integrity fresh source exit code"
        Set-Content -LiteralPath (Join-Path $root "project/source.txt") -Value "source-v2" -NoNewline
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root generated-integrity 2>&1) | Out-Null
        Assert-Equal 1 $LASTEXITCODE "generated-integrity source-stale exit code"
    }
}
Invoke-TestCase "materialized Defaults record final file provenance" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        $pack = $defaults.packs.pwa
        $baseVersion = (Get-Content -Raw -Encoding UTF8 (Join-Path $root ".kinotch/BASE_VERSION")).Trim()
        Assert-Equal $baseVersion $pack.source_base_version "PWA Default source Base version"
        $manifestFile = @($pack.materialized_files | Where-Object { $_.path -eq "project/public/manifest.webmanifest" })
        Assert-Equal 1 $manifestFile.Count "PWA manifest provenance entry"
        Assert-True ([string]$manifestFile[0].sha256 -match "^[0-9a-f]{64}$") "PWA provenance hash"
    }
}
Invoke-TestCase "unchanged Default provenance does not remove current files on upgrade" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router migrate --apply --default pwa 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "unchanged Default upgrade exit code"
        Assert-True (Test-Path (Join-Path $root "project/public/manifest.webmanifest")) "unchanged Default upgrade removed the manifest"
        Assert-True (Test-Path (Join-Path $root "project/public/service-worker.js")) "unchanged Default upgrade removed the service worker"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.pwa.state "unchanged Default upgrade state"
        Assert-True (@($defaults.packs.pwa.materialized_files).Count -gt 0) "unchanged Default upgrade lost provenance"
    }
}
Invoke-TestCase "doctor rejects a modified provenance-tracked Default" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        Add-Content -LiteralPath (Join-Path $root "project/public/service-worker.js") -Value "// project modification"
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        $doctorOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root doctor 2>&1)
        Assert-Equal 1 $LASTEXITCODE "modified Default doctor exit code"
        Assert-True (($doctorOutput -join "`n") -match "DEFAULT implementation was modified|provenance|OVERRIDE") "modified Default was not reported"
    }
}
Invoke-TestCase "PWA init and migrate use the same finalization" {
    $script:pwaInitParity = $null
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -AssertOutput {
        param($root, $output)
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/public/manifest.webmanifest") | ConvertFrom-Json
        $script:pwaInitParity = @{
            name = [string]$manifest.name
            short_name = [string]$manifest.short_name
            start_url = [string]$manifest.start_url
            display = [string]$manifest.display
        }
    }
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.project.name = $script:pwaInitParity.name
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root migrate --apply --default pwa 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "PWA migrate apply exit code"
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/public/manifest.webmanifest") | ConvertFrom-Json
        foreach ($field in @("name", "short_name", "start_url", "display")) {
            Assert-Equal $script:pwaInitParity[$field] ([string]$manifest.$field) "PWA parity $field"
        }
    }
}
Invoke-TestCase "Default materialization is atomic when an init template conflicts" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("pwa") -Prepare {
        param($root)
        $conflict = Join-Path $root ".kinotch/templates/project/public/service-worker.js"
        New-Item -ItemType Directory -Path (Split-Path -Parent $conflict) -Force | Out-Null
        Set-Content -LiteralPath $conflict -Value "project-owned-service-worker" -NoNewline
    } -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "OVERRIDE" $defaults.packs.pwa.state "init conflict state"
        Assert-Equal "project-owned-service-worker" (Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/public/service-worker.js")) "init conflict file"
        foreach ($relative in @(
            "project/public/manifest.webmanifest",
            "project/src/pwa/register.js",
            "project/tools/pwa-check.ps1"
        )) {
            Assert-True (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) "init partially materialized $relative"
        }
        Assert-True ($output -match "no Default files were materialized|OVERRIDE") "init conflict output was not reported"
    }
}
Invoke-TestCase "Default materialization is atomic for first middle and last conflicts" {
    foreach ($conflictRelative in @(
        "project/public/manifest.webmanifest",
        "project/public/service-worker.js",
        "project/tools/pwa-check.ps1"
    )) {
        Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
            param($root)
            $manifestPath = Join-Path $root "project/project.json"
            $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
            $manifest.surfaces.web = $true
            [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
            $conflictPath = Join-Path $root $conflictRelative
            New-Item -ItemType Directory -Path (Split-Path -Parent $conflictPath) -Force | Out-Null
            Set-Content -LiteralPath $conflictPath -Value ("project-owned-" + $conflictRelative) -NoNewline
        } -AssertOutput {
            param($root, $output)
            $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
            Assert-Equal "OVERRIDE" $defaults.packs.pwa.state "migrate conflict state"
            $conflictPath = Join-Path $root $conflictRelative
            Assert-Equal ("project-owned-" + $conflictRelative) (Get-Content -Raw -Encoding UTF8 $conflictPath) "migrate conflict file"
            foreach ($relative in @(
                "project/public/manifest.webmanifest",
                "project/public/service-worker.js",
                "project/src/pwa/register.js",
                "project/tools/pwa-check.ps1"
            )) {
                if ($relative -ne $conflictRelative) {
                    Assert-True (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) "migrate partially materialized $relative for $conflictRelative"
                }
            }
            Assert-True ($output -match "no Default files were materialized|OVERRIDE") "migrate conflict output was not reported"
        }
    }
}
Invoke-TestCase "identical Default files are preserved while missing siblings materialize" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $template = Join-Path $root ".kinotch/templates/defaults/pwa/public/service-worker.js"
        $existing = Join-Path $root "project/public/service-worker.js"
        New-Item -ItemType Directory -Path (Split-Path -Parent $existing) -Force | Out-Null
        Copy-Item -LiteralPath $template -Destination $existing
    } -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.pwa.state "identical Default state"
        foreach ($relative in @(
            "project/public/manifest.webmanifest",
            "project/src/pwa/register.js",
            "project/tools/pwa-check.ps1"
        )) {
            Assert-True (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf) "missing sibling was not materialized: $relative"
        }
    }
}
Invoke-TestCase "file and generated-integrity Defaults reject paths outside Project root" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("file-io", "generated-integrity") -AssertOutput {
        param($root, $output)
        $projectRoot = Join-Path $root "project"
        $outsideRoot = Join-Path (Split-Path -Parent $root) ((Split-Path -Leaf $root) + "-other")
        New-Item -ItemType Directory -Path $outsideRoot -Force | Out-Null
        $outsidePath = Join-Path $outsideRoot "outside.txt"
        Set-Content -LiteralPath $outsidePath -Value "outside" -NoNewline
        $updater = Join-Path $projectRoot "tools/update-generated-integrity.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $updater -Root $outsideRoot -Source "source.txt" -Artifact "generated.txt" -Generator test 2>&1) | Out-Null
        Assert-True ($LASTEXITCODE -ne 0) "generated-integrity accepted a caller-supplied Root"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $updater -Source "..\outside.txt" -Artifact "generated.txt" -Generator test 2>&1) | Out-Null
        Assert-True ($LASTEXITCODE -ne 0) "generated-integrity updater accepted a parent path"
        $fileIo = Join-Path $projectRoot "tools/file-io.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $fileIo -Action save -Path "inside.txt" -Content "changed" -Root $outsideRoot 2>&1) | Out-Null
        Assert-True ($LASTEXITCODE -ne 0) "file-io accepted a caller-supplied Root"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $fileIo -Action save -Path "..\outside.txt" -Content "changed" 2>&1) | Out-Null
        Assert-True ($LASTEXITCODE -ne 0) "file-io accepted a parent path"
        $absolutePath = Join-Path $outsideRoot "absolute.txt"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $fileIo -Action save -Path $absolutePath -Content "changed" 2>&1) | Out-Null
        Assert-True ($LASTEXITCODE -ne 0) "file-io accepted an absolute path"
        Assert-Equal "outside" (Get-Content -Raw -Encoding UTF8 $outsidePath) "outside file was modified"
        Remove-Item -LiteralPath $outsideRoot -Recurse -Force
    }
}
Invoke-TestCase "file-io rejects a symlink destination" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("file-io") -AssertOutput {
        param($root, $output)
        $projectRoot = Join-Path $root "project"
        $outside = Join-Path $root "outside-target"
        New-Item -ItemType Directory -Path $outside -Force | Out-Null
        $link = Join-Path $projectRoot "link"
        try {
            New-Item -ItemType SymbolicLink -Path $link -Target $outside -ErrorAction Stop | Out-Null
        }
        catch {
            $script:SkipCurrentTest = $true
            Write-Host "[SKIP] symlink creation is unavailable: $($_.Exception.Message)" -ForegroundColor Yellow
            return
        }
        try {
            $fileIo = Join-Path $projectRoot "tools/file-io.ps1"
            @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $fileIo -Action save -Path "link/escaped.txt" -Content "blocked" 2>&1) | Out-Null
            Assert-True ($LASTEXITCODE -ne 0) "file-io crossed a symlink boundary"
            Assert-True (-not (Test-Path (Join-Path $outside "escaped.txt"))) "file-io wrote through a symlink"
        }
        finally {
            Remove-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
        }
    }
}
Invoke-TestCase "generated-integrity rejects a symlink source" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("generated-integrity") -AssertOutput {
        param($root, $output)
        $projectRoot = Join-Path $root "project"
        $outside = Join-Path $root "outside-target"
        New-Item -ItemType Directory -Path $outside -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $outside "source.txt") -Value "outside" -NoNewline
        Set-Content -LiteralPath (Join-Path $projectRoot "generated.txt") -Value "artifact" -NoNewline
        $link = Join-Path $projectRoot "link"
        try {
            New-Item -ItemType SymbolicLink -Path $link -Target $outside -ErrorAction Stop | Out-Null
        }
        catch {
            $script:SkipCurrentTest = $true
            Write-Host "[SKIP] symlink creation is unavailable: $($_.Exception.Message)" -ForegroundColor Yellow
            return
        }
        try {
            $updater = Join-Path $projectRoot "tools/update-generated-integrity.ps1"
            @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $updater -Source "link/source.txt" -Artifact "generated.txt" -Generator test 2>&1) | Out-Null
            Assert-True ($LASTEXITCODE -ne 0) "generated-integrity crossed a symlink boundary"
        }
        finally {
            Remove-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
        }
    }
}
Invoke-TestCase "command cwd rejects a symlink boundary" {
    Invoke-KntFixture -Name "valid-minimal" -Command "test" -ExpectedExit 1 -Prepare {
        param($root)
        $outside = Join-Path $root "outside-target"
        New-Item -ItemType Directory -Path $outside -Force | Out-Null
        $link = Join-Path $root "project/link"
        try {
            New-Item -ItemType SymbolicLink -Path $link -Target $outside -ErrorAction Stop | Out-Null
        }
        catch {
            $script:SkipCurrentTest = $true
            Write-Host "[SKIP] symlink creation is unavailable: $($_.Exception.Message)" -ForegroundColor Yellow
            return
        }
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{
            run = "Get-Location | Out-File command-cwd.marker"
            cwd = "project/link"
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "symlink|junction|reparse|boundary") "command cwd symlink boundary was not reported"
    }
}
Invoke-TestCase "Default upgrade removes an unchanged stale file" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $catalogPath = Join-Path $root ".kinotch/defaults/catalog.json"
        $catalog = Get-Content -Raw -Encoding UTF8 $catalogPath | ConvertFrom-Json
        ($catalog.defaults | Where-Object id -eq "pwa") | Add-Member -NotePropertyName retired_paths -NotePropertyValue @("project/public/legacy.js") -Force
        [IO.File]::WriteAllText($catalogPath, (ConvertTo-Json $catalog -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $stalePath = Join-Path $root "project/public/legacy.js"
        New-Item -ItemType Directory -Path (Split-Path -Parent $stalePath) -Force | Out-Null
        Set-Content -LiteralPath $stalePath -Value "legacy" -NoNewline
        $staleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stalePath).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{
                pwa = [pscustomobject]@{
                    state = "DEFAULT"
                    source_base_version = "0.5.1"
                    materialized_files = @([pscustomobject]@{ path = "project/public/legacy.js"; sha256 = $staleHash })
                }
            }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (-not (Test-Path (Join-Path $root "project/public/legacy.js"))) "unchanged stale Default file was not removed"
        Assert-True (Test-Path (Join-Path $root "project/public/manifest.webmanifest")) "new Default file was not materialized"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-True (@($defaults.packs.pwa.materialized_files | Where-Object { $_.path -eq "project/public/legacy.js" }).Count -eq 0) "stale path remained in provenance"
    }
}
Invoke-TestCase "Default upgrade preserves a modified stale file and records OVERRIDE" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $catalogPath = Join-Path $root ".kinotch/defaults/catalog.json"
        $catalog = Get-Content -Raw -Encoding UTF8 $catalogPath | ConvertFrom-Json
        ($catalog.defaults | Where-Object id -eq "pwa") | Add-Member -NotePropertyName retired_paths -NotePropertyValue @("project/public/legacy.js") -Force
        [IO.File]::WriteAllText($catalogPath, (ConvertTo-Json $catalog -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $stalePath = Join-Path $root "project/public/legacy.js"
        New-Item -ItemType Directory -Path (Split-Path -Parent $stalePath) -Force | Out-Null
        Set-Content -LiteralPath $stalePath -Value "legacy" -NoNewline
        $recordedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stalePath).Hash.ToLowerInvariant()
        Set-Content -LiteralPath $stalePath -Value "modified" -NoNewline
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{
                pwa = [pscustomobject]@{
                    state = "DEFAULT"
                    source_base_version = "0.5.1"
                    materialized_files = @([pscustomobject]@{ path = "project/public/legacy.js"; sha256 = $recordedHash })
                }
            }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "OVERRIDE" $defaults.packs.pwa.state "modified stale Default state"
        Assert-Equal "modified" (Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/public/legacy.js")) "modified stale file"
        Assert-True (-not (Test-Path (Join-Path $root "project/public/manifest.webmanifest"))) "conflicting stale file did not preserve atomicity"
        Assert-True ($output -match "conflict|OVERRIDE") "modified stale conflict was not reported"
    }
}
Invoke-TestCase "DISABLED Default dry-run reports tracked cleanup without writing" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $filePath = Join-Path $root "project/public/manifest.webmanifest"
        New-Item -ItemType Directory -Path (Split-Path -Parent $filePath) -Force | Out-Null
        Set-Content -LiteralPath $filePath -Value "disabled" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ pwa = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/public/manifest.webmanifest"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (Test-Path (Join-Path $root "project/public/manifest.webmanifest")) "DISABLED dry-run removed a file"
        Assert-True ($output -match "DISABLED.*scheduled for removal") "DISABLED cleanup was not reported"
    }
}
Invoke-TestCase "DISABLED Default apply removes unchanged tracked files" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $filePath = Join-Path $root "project/public/manifest.webmanifest"
        New-Item -ItemType Directory -Path (Split-Path -Parent $filePath) -Force | Out-Null
        Set-Content -LiteralPath $filePath -Value "disabled" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ pwa = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/public/manifest.webmanifest"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (-not (Test-Path (Join-Path $root "project/public/manifest.webmanifest"))) "DISABLED apply preserved an unchanged file"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DISABLED" $defaults.packs.pwa.state "DISABLED state changed during cleanup"
        Assert-True ($null -eq $defaults.packs.pwa.PSObject.Properties["materialized_files"]) "DISABLED provenance was not cleared"
    }
}
Invoke-TestCase "explicitly selected DISABLED Tool Default still reconciles" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "logging") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $filePath = Join-Path $root "project/tools/logging-default.ps1"
        New-Item -ItemType Directory -Path (Split-Path -Parent $filePath) -Force | Out-Null
        Set-Content -LiteralPath $filePath -Value "disabled" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ logging = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/tools/logging-default.ps1"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (-not (Test-Path (Join-Path $root "project/tools/logging-default.ps1"))) "selected DISABLED Tool Default was not reconciled"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DISABLED" $defaults.packs.logging.state "selected DISABLED Tool state changed"
        Assert-True ($null -eq $defaults.packs.logging.PSObject.Properties["materialized_files"]) "selected DISABLED Tool provenance remained"
    }
}
Invoke-TestCase "explicitly selected DISABLED Surface Default still reconciles" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--profile", "cli") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.profile = "cli"
        $manifest.surfaces.cli = $true
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $filePath = Join-Path $root "project/tools/cli-default.ps1"
        New-Item -ItemType Directory -Path (Split-Path -Parent $filePath) -Force | Out-Null
        Set-Content -LiteralPath $filePath -Value "disabled" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ cli = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/tools/cli-default.ps1"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (-not (Test-Path (Join-Path $root "project/tools/cli-default.ps1"))) "selected DISABLED Surface Default was not reconciled"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DISABLED" $defaults.packs.cli.state "selected DISABLED Surface state changed"
    }
}
Invoke-TestCase "doctor rejects a modified DISABLED materialized file" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $filePath = Join-Path $root "project/public/manifest.webmanifest"
        New-Item -ItemType Directory -Path (Split-Path -Parent $filePath) -Force | Out-Null
        Set-Content -LiteralPath $filePath -Value "original" -NoNewline
        $oldHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        Set-Content -LiteralPath $filePath -Value "modified" -NoNewline
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ pwa = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/public/manifest.webmanifest"; sha256 = $oldHash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "DISABLED.*modified|mark the pack OVERRIDE") "modified DISABLED file was not rejected"
    }
}
Invoke-TestCase "DISABLED cleanup does not trust unrelated provenance paths" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $unrelated = Join-Path $root "README.md"
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $unrelated).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ logging = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "README.md"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (Test-Path (Join-Path $root "README.md")) "unrelated provenance path was deleted"
        Assert-True ($output -match "untrusted|conflict|README\.md") "untrusted provenance was not reported"
    }
}
Invoke-TestCase "retired Default paths are trusted only when declared by the catalog" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $catalogPath = Join-Path $root ".kinotch/defaults/catalog.json"
        $catalog = Get-Content -Raw -Encoding UTF8 $catalogPath | ConvertFrom-Json
        ($catalog.defaults | Where-Object id -eq "logging") | Add-Member -NotePropertyName retired_paths -NotePropertyValue @("project/tools/retired-helper.ps1") -Force
        [IO.File]::WriteAllText($catalogPath, (ConvertTo-Json $catalog -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $retired = Join-Path $root "project/tools/retired-helper.ps1"
        New-Item -ItemType Directory -Path (Split-Path -Parent $retired) -Force | Out-Null
        Set-Content -LiteralPath $retired -Value "retired" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $retired).Hash.ToLowerInvariant()
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ logging = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/tools/retired-helper.ps1"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (-not (Test-Path (Join-Path $root "project/tools/retired-helper.ps1"))) "declared retired Default path was not removed"
    }
}
Invoke-TestCase "modified retired Default paths remain protected" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $catalogPath = Join-Path $root ".kinotch/defaults/catalog.json"
        $catalog = Get-Content -Raw -Encoding UTF8 $catalogPath | ConvertFrom-Json
        ($catalog.defaults | Where-Object id -eq "logging") | Add-Member -NotePropertyName retired_paths -NotePropertyValue @("project/tools/retired-helper.ps1") -Force
        [IO.File]::WriteAllText($catalogPath, (ConvertTo-Json $catalog -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        $retired = Join-Path $root "project/tools/retired-helper.ps1"
        New-Item -ItemType Directory -Path (Split-Path -Parent $retired) -Force | Out-Null
        Set-Content -LiteralPath $retired -Value "original" -NoNewline
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $retired).Hash.ToLowerInvariant()
        Set-Content -LiteralPath $retired -Value "modified" -NoNewline
        $defaults = [pscustomobject]@{ schema_version = 1; packs = [pscustomobject]@{ logging = [pscustomobject]@{ state = "DISABLED"; materialized_files = @([pscustomobject]@{ path = "project/tools/retired-helper.ps1"; sha256 = $hash }) } } }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-Equal "modified" (Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/tools/retired-helper.ps1")) "modified retired path was deleted"
        Assert-True ($output -match "modified|OVERRIDE|conflict") "modified retired path conflict was not reported"
    }
}
Invoke-TestCase "unknown catalog Default is rejected" {
    Invoke-KntInitFixture -Profiles @("web-app") -Defaults @("not-a-default") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Unknown.*Default|catalog") "unknown Default was not reported"
    }
}
Invoke-TestCase "init refuses to overwrite an existing Project" {
    $router = Join-Path $RepoRoot ".kinotch/scripts/knt.ps1"
    $output = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router init --profile cli 2>&1)
    $exitCode = $LASTEXITCODE
    Assert-Equal 1 $exitCode "init refusal exit code"
    Assert-True (($output -join [Environment]::NewLine) -match "already initialized|project/project.json") "init refusal was not reported"
}
Invoke-TestCase "migrate dry-run reports candidates without writing" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--profile", "cli") -ExpectedExit 0 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Candidate Default Pack.*cli") "migrate candidate was not reported"
        Assert-True ($output -match "no files changed|--apply") "migrate dry-run warning was not reported"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "migrate dry-run wrote a file"
    }
}
Invoke-TestCase "migrate dry-run warns when an explicit Surface is not enabled" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--profile", "cli") -ExpectedExit 0 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "NOT ENABLED IN MANIFEST") "migrate dry-run did not warn about a disabled Surface"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "Surface dry-run wrote a Default state"
    }
}
Invoke-TestCase "migrate apply rejects an explicit Surface not enabled in Manifest" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--profile", "cli") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "NOT ENABLED IN MANIFEST|requires.*enabled|not enabled") "migrate apply accepted a disabled Surface"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "disabled Surface apply wrote a Default state"
    }
}
Invoke-TestCase "migrate rejects removed Tool Default aliases" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--default", "verify") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Unknown.*Default|catalog") "removed verify alias was accepted"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "Tool Default dry-run wrote a file"
    }
}
Invoke-TestCase "migrate detects Web, PWA, and CI shape without a Base Manifest" {
    Invoke-KntShapeMigrateFixture -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "web-app") "web-app shape was not detected"
        Assert-True ($output -match "ci-test") "ci-test shape was not detected"
        Assert-True ($output -match "pwa") "pwa shape was not detected"
        Assert-True ($output -match "Candidate Default Pack 'ci-test': state OVERRIDE") "existing CI implementation was not classified as OVERRIDE"
        Assert-True ($output -match "Candidate Default Pack 'pwa': state OVERRIDE") "existing PWA implementation was not classified as OVERRIDE"
        Assert-True ($output -match "Candidate Default Pack 'web-app': state OVERRIDE") "existing Web implementation was not classified as OVERRIDE"
        Assert-True ($output -notmatch "Detected Surface candidates:.*cli") "test/build scripts were misclassified as CLI"
        Assert-True ($output -notmatch "Detected Tool candidates:.*verify") "L1 verify was misreported as a Tool Default"
        Assert-True ($output -match "Dry run") "shape migrate was not dry-run"
    }
}
Invoke-TestCase "shape probe distinguishes deploy-only and verification CI" {
    Invoke-KntShapeMigrateFixture -WorkflowText "name: Deploy`nrun: wrangler deploy" -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Candidate Default Pack 'ci-test': state DEFAULT") "deploy-only workflow was marked OVERRIDE"
    }
    Invoke-KntShapeMigrateFixture -WorkflowText "name: Verify`nrun: npm test" -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Candidate Default Pack 'ci-test': state OVERRIDE") "verification workflow was not marked OVERRIDE"
    }
}
Invoke-TestCase "shape probe ignores the Base common verification workflow" {
    Invoke-KntShapeMigrateFixture -UseBaseWorkflow -AssertOutput {
        param($root, $output)
        Assert-True ($output -notmatch "Candidate Default Pack 'ci-test'") "Base common workflow was misclassified as an L2 ci-test Default"
    }
}
Invoke-TestCase "shape probe isolates incidental repository workflows" {
    $incidentalVerification = "name: Maintenance Verify`nrun: npm test"
    $incidentalDeploy = "name: Maintenance Deploy`nrun: wrangler deploy"
    Invoke-KntShapeMigrateFixture -WorkflowText "name: Deploy`nrun: wrangler deploy" -IncidentalWorkflowText $incidentalVerification -AssertOutput {
        param($root, $output)
        $workflowFiles = @(Get-ChildItem -LiteralPath (Join-Path $root ".github/workflows") -File)
        Assert-Equal 1 $workflowFiles.Count "deploy-only isolated workflow count"
        Assert-Equal "verify.yml" $workflowFiles[0].Name "deploy-only isolated workflow name"
        Assert-True ($output -match "Candidate Default Pack 'ci-test': state DEFAULT") "incidental verification workflow contaminated deploy-only fixture"
    }
    Invoke-KntShapeMigrateFixture -WorkflowText "name: Verify`nrun: npm test" -IncidentalWorkflowText $incidentalDeploy -AssertOutput {
        param($root, $output)
        $workflowFiles = @(Get-ChildItem -LiteralPath (Join-Path $root ".github/workflows") -File)
        Assert-Equal 1 $workflowFiles.Count "verification isolated workflow count"
        Assert-Equal "verify.yml" $workflowFiles[0].Name "verification isolated workflow name"
        Assert-True ($output -match "Candidate Default Pack 'ci-test': state OVERRIDE") "intended verification workflow was not preserved"
    }
    Invoke-KntShapeMigrateFixture -UseBaseWorkflow -IncidentalWorkflowText $incidentalVerification -AssertOutput {
        param($root, $output)
        $workflowFiles = @(Get-ChildItem -LiteralPath (Join-Path $root ".github/workflows") -File)
        Assert-Equal 1 $workflowFiles.Count "Base-workflow isolated workflow count"
        Assert-Equal "verify.yml" $workflowFiles[0].Name "Base-workflow isolated workflow name"
        Assert-True ($output -notmatch "Candidate Default Pack 'ci-test'") "incidental workflow contaminated Base-common-workflow fixture"
    }
}
Invoke-TestCase "shape probe distinguishes generated files from integrity checks" {
    Invoke-KntShapeMigrateFixture -GeneratedFile -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Candidate Default Pack 'generated-integrity': state DEFAULT") "generated file was incorrectly marked OVERRIDE"
    }
    Invoke-KntShapeMigrateFixture -GeneratedFile -IntegrityEvidence -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Candidate Default Pack 'generated-integrity': state OVERRIDE") "integrity evidence was not marked OVERRIDE"
    }
}
Invoke-TestCase "shape probe ignores vendored public integrity text" {
    Invoke-KntShapeMigrateFixture -VendorIntegrityEvidence -AssertOutput {
        param($root, $output)
        Assert-True ($output -notmatch "Candidate Default Pack 'generated-integrity'") "vendored public integrity text was misclassified as Project generated-integrity"
    }
}
Invoke-TestCase "shape probe filters incompatible Tool evidence" {
    Invoke-KntShapeMigrateFixture -AgentRoot -NoWebAssets -UseBaseWorkflow -IntegrityEvidence -PackageJson '{"scripts":{"test":"python -m unittest"}}' -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Detected Surface candidates:.*agent") "Agent shape was not detected"
        Assert-True ($output -notmatch "Candidate Default Pack 'generated-integrity'") "incompatible generated-integrity evidence was offered to Agent shape"
    }
}
Invoke-TestCase "shape probe does not treat Wrangler-only Web as API" {
    Invoke-KntShapeMigrateFixture -PackageJson '{"scripts":{"test":"node --test","build":"npm run build"},"devDependencies":{"wrangler":"latest"}}' -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Detected Surface candidates:.*web-app") "Wrangler-only Web surface was not detected"
        Assert-True ($output -notmatch "Detected Surface candidates:.*api") "Wrangler-only Web project was misclassified as API"
    }
}
Invoke-TestCase "shape probe still detects Hono API" {
    Invoke-KntShapeMigrateFixture -PackageJson '{"dependencies":{"hono":"latest"}}' -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Detected Surface candidates:.*api") "Hono API surface was not detected"
    }
}
Invoke-TestCase "migrate apply preserves Project override and adds missing pack" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--profile", "cli", "--profile", "mcp") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.cli = $true
        $manifest.surfaces.mcp = $true
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{
                cli = [pscustomobject]@{ state = "OVERRIDE"; notes = "Project-owned CLI" }
                mcp = [pscustomobject]@{ state = "DISABLED"; notes = "Project does not expose MCP" }
            }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "OVERRIDE" $defaults.packs.cli.state "existing override state"
        Assert-Equal "DISABLED" $defaults.packs.mcp.state "existing disabled state"
        Assert-True ($output -match "preserved.*OVERRIDE") "override preservation was not reported"
    }
}
Invoke-TestCase "migrate apply materializes missing safe Tool Default files" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True (Test-Path -LiteralPath (Join-Path $root "project/public/manifest.webmanifest") -PathType Leaf) "migrate apply did not materialize PWA manifest"
        Assert-True (Test-Path -LiteralPath (Join-Path $root "project/tools/pwa-check.ps1") -PathType Leaf) "migrate apply did not materialize PWA checker"
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "DEFAULT" $defaults.packs.pwa.state "migrate applied Tool Default state"
        Assert-True ($output -match "Tool Default 'pwa' materialized") "migrate apply did not report materialized PWA files"
    }
}
Invoke-TestCase "migrate apply records conflicting Default files as OVERRIDE" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $manifestPath = Join-Path $root "project/public/manifest.webmanifest"
        New-Item -ItemType Directory -Path (Split-Path -Parent $manifestPath) -Force | Out-Null
        Set-Content -LiteralPath $manifestPath -Value '{"name":"Project-owned","start_url":"/custom"}' -NoNewline
    } -AssertOutput {
        param($root, $output)
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/defaults.json") | ConvertFrom-Json
        Assert-Equal "OVERRIDE" $defaults.packs.pwa.state "conflicting PWA Default state"
        $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/public/manifest.webmanifest") | ConvertFrom-Json
        Assert-Equal "/custom" $manifest.start_url "existing PWA file was overwritten"
        Assert-True ($output -match "conflict|OVERRIDE") "materialization conflict was not reported"
    }
}
Invoke-TestCase "migrate rejects an incompatible Tool Default from existing Manifest surfaces" {
    Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "pwa") -ExpectedExit 2 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.cli = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "not compatible") "migrate accepted an incompatible Tool Default"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "incompatible migrate wrote Default state"
    }
}
Invoke-TestCase "doctor rejects a hand-edited incompatible DEFAULT Tool" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{ pwa = [pscustomobject]@{ state = "DEFAULT" } }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "not compatible|incompatible.*Surface") "doctor accepted an incompatible DEFAULT Tool"
    }
}
Invoke-TestCase "doctor rejects a hand-edited DEFAULT Surface disabled in Manifest" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{ cli = [pscustomobject]@{ state = "DEFAULT" } }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Surface.*cli.*not enabled|cli.*not enabled|incompatible.*Surface") "doctor accepted a disabled DEFAULT Surface"
    }
}
Invoke-TestCase "external BaseOverride rejects init and migrate writes" {
    Invoke-KntExternalBaseFixture -Command "init" -Arguments @("--profile", "web-app") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "repository-local.*\.kinotch|read-only") "external Base init write was not rejected"
        Assert-True (-not (Test-Path (Join-Path $root "project"))) "external Base init created Project files"
    }
    Invoke-KntExternalBaseFixture -FixtureName "valid-minimal" -Command "migrate" -Arguments @("--apply", "--default", "ci-test") -ExpectedExit 2 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.surfaces.web = $true
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "repository-local.*\.kinotch|read-only") "external Base migrate write was not rejected"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "external Base migrate wrote Default state"
    }
}
Invoke-TestCase "manifest-less migrate apply is rejected before writing" {
    Invoke-KntExternalBaseFixture -Command "migrate" -Arguments @("--apply", "--profile", "web-app") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "existing Project Manifest|repository-local.*\.kinotch|read-only") "manifest-less apply rejection was not reported"
        Assert-True (-not (Test-Path (Join-Path $root "project/defaults.json"))) "manifest-less apply wrote Default state"
    }
}
Invoke-TestCase "doctor rejects an unknown Default catalog id" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.paths | Add-Member -NotePropertyName defaults -NotePropertyValue "defaults.json" -Force
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $defaults = [pscustomobject]@{
            schema_version = 1
            packs = [pscustomobject]@{ not_a_default = [pscustomobject]@{ state = "DEFAULT" } }
        }
        [IO.File]::WriteAllText((Join-Path $root "project/defaults.json"), (ConvertTo-Json $defaults -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Unknown.*Default|catalog") "unknown catalog Default was not reported by doctor"
    }
}
Invoke-TestCase "doctor rejects duplicate Default catalog identifiers and aliases" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 2 -Prepare {
        param($root)
        $catalogPath = Join-Path $root ".kinotch/defaults/catalog.json"
        $catalog = Get-Content -Raw -Encoding UTF8 $catalogPath | ConvertFrom-Json
        $catalog.defaults[1].aliases = @("cli")
        [IO.File]::WriteAllText($catalogPath, (ConvertTo-Json $catalog -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "semantic|alias|duplicate|collision") "catalog alias collision was not rejected"
    }
}
Invoke-TestCase "removed candidate Defaults are rejected" {
    foreach ($removed in @("pages", "secrets", "local-app", "verify-binding")) {
        Invoke-KntFixture -Name "valid-minimal" -Command "migrate" -Arguments @("--default", $removed) -ExpectedExit 2 -AssertOutput {
            param($root, $output)
            Assert-True ($output -match "Unknown.*Default|catalog") "removed Default was accepted"
        }
    }
}
Invoke-TestCase "Windows helper uses a Windows PowerShell 5.1-compatible host check" {
    $helper = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/templates/defaults/windows/tools/windows-shell.ps1")
    Assert-True ($helper -match '\$env:OS\s*-eq\s*"Windows_NT"') "Windows helper does not use the Windows_NT environment marker"
    Assert-True ($helper -notmatch '\$IsWindows') "Windows helper relies on the PowerShell Core-only IsWindows variable"
}
Invoke-TestCase "Windows Surface Kit provides path, drop, picker, progress, and cancel helpers" {
    Invoke-KntInitFixture -Profiles @("windows-gui") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/windows-shell.ps1"
        $probe = Join-Path $root "windows-kit-probe.ps1"
        $existing = Join-Path $root "project/input.txt"
        Set-Content -LiteralPath $existing -Value "input" -Encoding UTF8
        $probeText = @'
param(
    [Parameter(Mandatory=$true)][string]$HelperPath,
    [Parameter(Mandatory=$true)][string]$ExistingPath
)
$ErrorActionPreference = "Stop"
. $HelperPath
$normalized = Resolve-WindowsShellPath -Path $ExistingPath
if ($normalized -ne (Resolve-Path -LiteralPath $ExistingPath).Path) { throw "path was not normalized" }
$drop = @(Convert-WindowsDropItems -Paths @($ExistingPath, "", "  "))
if ($drop.Count -ne 1 -or $drop[0] -ne $normalized) { throw "drop paths were not normalized" }
if ($null -ne (Convert-WindowsDropItems -Paths @("", "  "))) { throw "empty drop was not cancelled" }
if ((Select-WindowsPath -Kind File -SelectedPath "") -ne $null) { throw "cancelled file picker did not return null" }
if ((Save-WindowsPath -SelectedPath "") -ne $null) { throw "cancelled save picker did not return null" }
$cancel = New-WindowsCancelSource
if (Test-WindowsCancelRequested -Source $cancel) { throw "new cancel source is already requested" }
Request-WindowsCancel -Source $cancel
if (-not (Test-WindowsCancelRequested -Source $cancel)) { throw "cancel request was not observed" }
$progress = New-WindowsProgressState -Stage "load" -Total 2
if ($progress.status -ne "started") { throw "progress did not start" }
Update-WindowsProgressState -State $progress -Current 1 -Message "half"
if ($progress.status -ne "progress" -or $progress.current -ne 1 -or $progress.message -ne "half") { throw "progress update was not recorded" }
Complete-WindowsProgressState -State $progress
if ($progress.status -ne "completed") { throw "progress did not complete" }
$failed = New-WindowsProgressState -Stage "save" -Total 1
Fail-WindowsProgressState -State $failed -Message "failed"
if ($failed.status -ne "failed" -or $failed.message -ne "failed") { throw "progress failure was not recorded" }
Write-Output "windows-kit-ok"
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $probeOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper -ExistingPath $existing 2>&1)
        Assert-Equal 0 $LASTEXITCODE "Windows Surface Kit probe exit code"
        Assert-True (($probeOutput -join "`n") -match "windows-kit-ok") "Windows Surface Kit probe did not complete"
    }
}
Invoke-TestCase "MCP Surface Kit describes reusable boundary hooks without a second registry" {
    Invoke-KntInitFixture -Profiles @("mcp") -AssertOutput {
        param($root, $output)
        $descriptor = Get-Content -Raw -Encoding UTF8 (Join-Path $root "project/contracts/mcp-tools.json") | ConvertFrom-Json
        Assert-True ($descriptor.tool_name_pattern -eq '^[a-z][a-z0-9_.-]*$') "MCP naming boundary changed"
        Assert-True ($descriptor.input_schema_validation -eq $true) "MCP input validation hook missing"
        Assert-True ($descriptor.resource_path_resolution -eq $true) "MCP resource path resolution missing"
        Assert-True ($descriptor.error_conversion -eq $true) "MCP error conversion boundary missing"
        Assert-True ($descriptor.dispatch.use_existing_framework -eq $true) "MCP descriptor requests a second dispatcher"
    }
}
Invoke-TestCase "MCP executable Surface Kit provides safe boundary helpers" {
    Invoke-KntInitFixture -Profiles @("mcp") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/mcp-default.ps1"
        Assert-True (Test-Path -LiteralPath $helper -PathType Leaf) "MCP executable helper was not materialized"
        $probe = Join-Path $root "mcp-kit-probe.ps1"
        $probeText = @'
param([Parameter(Mandatory=$true)][string]$HelperPath,[Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = "Stop"
. $HelperPath
if (-not (Test-McpToolName -Name "text.transform")) { throw "valid MCP tool name was rejected" }
if (Test-McpToolName -Name "Invalid Tool") { throw "invalid MCP tool name was accepted" }
$validated = Invoke-McpInputValidator -InputObject ([pscustomobject]@{ value = 1 }) -Validator { param($value) $script:validatorCalled = $true; return $value }
if (-not $script:validatorCalled -or $validated.value -ne 1) { throw "MCP validator callback was not invoked" }
$resolved = Resolve-McpProjectPath -ProjectRoot $ProjectRoot -RelativePath "src"
if (-not $resolved.StartsWith($ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "MCP path was not resolved under Project root" }
try { Resolve-McpProjectPath -ProjectRoot $ProjectRoot -RelativePath "../outside"; throw "MCP path escape was accepted" } catch { if ($_.Exception.Message -notmatch "relative|boundary|escape") { throw } }
$diagnostic = New-McpDiagnostic -Level "info" -Message "ready" -Data @{ source = "test" }
$errorEnvelope = New-McpErrorEnvelope -Code "invalid_input" -Message "bad" -Details @{ field = "value" }
$capabilities = New-McpCapabilities -Version "1.0.0" -Capabilities @("diagnostics")
if ($diagnostic.message -ne "ready" -or $errorEnvelope.error -ne "invalid_input" -or $capabilities.version -ne "1.0.0") { throw "MCP boundary helper output was incomplete" }
Write-Output "mcp-kit-ok"
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $probeOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper -ProjectRoot (Join-Path $root "project") 2>&1)
        Assert-Equal 0 $LASTEXITCODE "MCP executable helper probe exit code"
        Assert-True (($probeOutput -join "`n") -match "mcp-kit-ok") "MCP executable helper probe did not complete"
        $helperText = Get-Content -Raw -Encoding UTF8 $helper
        Assert-True ($helperText -notmatch "ActionRegistry|Tool Registry|function .*Dispatcher") "MCP helper introduced a second registry or dispatcher"
    }
}
Invoke-TestCase "Agent Surface Kit provides a dependency-free boundary" {
    Invoke-KntInitFixture -Profiles @("agent") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/agent-default.ps1"
        Assert-True (Test-Path -LiteralPath $helper -PathType Leaf) "Agent helper was not materialized"
        $probe = Join-Path $root "agent-kit-probe.ps1"
        $probeText = @'
param([Parameter(Mandatory=$true)][string]$HelperPath)
$ErrorActionPreference = "Stop"
. $HelperPath
$context = New-AgentInvocationContext -RequestId "req-1" -CorrelationId "corr-1" -InputObject @{ task = "run" } -Metadata @{ source = "test" }
if ($context.requestId -ne "req-1" -or $context.correlationId -ne "corr-1" -or $context.input.task -ne "run" -or $context.metadata.source -ne "test") { throw "Agent invocation context was not preserved" }
$diagnostic = New-AgentDiagnostic -Level "info" -Message "ready"
$report = New-AgentCapabilityReport -Version "1.0.0" -Capabilities @("invoke")
$hooked = Invoke-AgentBoundaryHook -Name "before" -Value "input" -Hook { param($value, $name) return ($value + "-" + $name) }
if ($diagnostic.message -ne "ready" -or $report.version -ne "1.0.0" -or $hooked -ne "input-before") { throw "Agent boundary helper output was incomplete" }
Write-Output "agent-kit-ok"
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $probeOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper 2>&1)
        Assert-Equal 0 $LASTEXITCODE "Agent helper probe exit code"
        Assert-True (($probeOutput -join "`n") -match "agent-kit-ok") "Agent helper probe did not complete"
        $helperText = Get-Content -Raw -Encoding UTF8 $helper
        Assert-True ($helperText -notmatch "Planner|Memory|AgentBackend|ResourceLedger") "Agent helper captured Project-owned policy"
    }
}
Invoke-TestCase "Base CI matrix and Project CI template have separate responsibilities" {
    $baseWorkflow = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".github/workflows/verify.yml")
    Assert-True ($baseWorkflow -match "matrix") "Base CI workflow lost its cross-platform matrix"
    Assert-True ($baseWorkflow -match "ubuntu-latest") "Base CI workflow is missing Ubuntu"
    Assert-True ($baseWorkflow -match "windows-latest") "Base CI workflow is missing Windows"
    Assert-True ($baseWorkflow -match "powershell") "Base CI workflow is missing Windows PowerShell 5.1"
    Assert-True ($baseWorkflow -match "pwsh") "Base CI workflow is missing PowerShell Core"

    $projectTemplate = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/templates/defaults/ci-test/.github/workflows/kinotch-default.yml")
    Assert-True ($projectTemplate -match "runs-on: ubuntu-latest") "Project CI template is missing the default Ubuntu runner"
    Assert-True ($projectTemplate -match "shell: pwsh") "Project CI template is missing PowerShell Core"
    Assert-True ($projectTemplate -notmatch "matrix|windows-latest|powershell") "Project CI template imposes the Base three-environment matrix"
}
Invoke-TestCase "Project ci-test selects one Surface-appropriate runner" {
    Invoke-KntInitFixture -Profiles @("cli") -Defaults @("ci-test") -RemoveExistingCi -AssertOutput {
        param($root, $output)
        $workflow = Get-Content -Raw -Encoding UTF8 (Join-Path $root ".github/workflows/kinotch-default.yml")
        Assert-True ($workflow -match "runs-on: ubuntu-latest") "CLI Project ci-test did not select Ubuntu"
        Assert-True ($workflow -notmatch "windows-latest|matrix") "CLI Project ci-test imposed a Windows or matrix runner"
    }
    Invoke-KntInitFixture -Profiles @("windows-gui") -Defaults @("ci-test") -RemoveExistingCi -AssertOutput {
        param($root, $output)
        $workflow = Get-Content -Raw -Encoding UTF8 (Join-Path $root ".github/workflows/kinotch-default.yml")
        Assert-True ($workflow -match "runs-on: windows-latest") "Windows Project ci-test did not select Windows"
        Assert-True ($workflow -notmatch "matrix") "Windows Project ci-test imposed a matrix runner"
    }
}
Invoke-TestCase "API Default envelope remains a permissive boundary descriptor" {
    $schema = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/templates/defaults/api/contracts/api-error-envelope.json") | ConvertFrom-Json
    Assert-True (@($schema.required) -notcontains "details") "API Default made details mandatory"
    Assert-True ($schema.additionalProperties -eq $true) "API Default rejects Project-owned extensions"
    Assert-True ($null -eq $schema.properties.details.type) "API Default details is narrower than the helper"
    $envelopes = @(
        [pscustomobject]@{ error = "invalid_input"; message = "bad"; details = @{ field = "value" } },
        [pscustomobject]@{ error = "invalid_input"; message = "bad"; details = @("value") },
        [pscustomobject]@{ error = "invalid_input"; message = "bad"; details = "value" },
        [pscustomobject]@{ error = "invalid_input"; message = "bad"; details = 7 },
        [pscustomobject]@{ error = "invalid_input"; message = "bad" }
    )
    foreach ($envelope in $envelopes) {
        Assert-Equal 0 @(Test-KntSchema -Data $envelope -Schema $schema -Path "fixture.api-error").Count "API envelope schema compatibility"
    }
}
Invoke-TestCase "API Surface Kit provides replaceable context, health, envelope, and hooks" {
    Invoke-KntInitFixture -Profiles @("api") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/api-default.ps1"
        Assert-True (Test-Path -LiteralPath $helper -PathType Leaf) "API Surface Kit helper was not materialized"
        $probe = Join-Path $root "api-kit-probe.ps1"
        $probeText = @'
param([Parameter(Mandatory=$true)][string]$HelperPath)
$ErrorActionPreference = "Stop"
. $HelperPath
$context = New-ApiRequestContext -RequestId "req-1" -CorrelationId "corr-1"
if ($context.requestId -ne "req-1" -or $context.correlationId -ne "corr-1") { throw "request context was not preserved" }
$generated = New-ApiRequestContext
if ([string]::IsNullOrWhiteSpace($generated.requestId) -or [string]::IsNullOrWhiteSpace($generated.correlationId)) { throw "request context IDs were not generated" }
$health = New-ApiHealthResponse -Name "sample"
if ($health.status -ne "ok" -or $health.name -ne "sample") { throw "health response was not created" }
$errorEnvelope = New-ApiErrorEnvelope -Code "invalid_input" -Message "bad input" -Details @{ field = "value" } -RequestId "req-1"
if ($errorEnvelope.error -ne "invalid_input" -or $errorEnvelope.message -ne "bad input" -or $errorEnvelope.requestId -ne "req-1") { throw "error envelope was not preserved" }
$hooked = Invoke-ApiHook -Name "validation" -Value "input" -Hook { param($value) return ($value + "-checked") }
if ($hooked -ne "input-checked") { throw "API hook was not invoked" }
$namedHook = Invoke-ApiHook -Name "auth" -Value "input" -Hook { param($value, $name) return ($value + "-" + $name) }
if ($namedHook -ne "input-auth") { throw "API hook name was not forwarded" }
$unchanged = Invoke-ApiHook -Name "auth" -Value "input"
if ($unchanged -ne "input") { throw "missing API hook changed the value" }
Write-Output "api-kit-ok"
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $probeOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper 2>&1)
        Assert-Equal 0 $LASTEXITCODE "API Surface Kit probe exit code"
        Assert-True (($probeOutput -join "`n") -match "api-kit-ok") "API Surface Kit probe did not complete"
    }
}
Invoke-TestCase "Config Tool Default merges maps and redacts only explicit keys" {
    Invoke-KntInitFixture -Profiles @("minimal") -Defaults @("config") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/config-default.ps1"
        Assert-True (Test-Path -LiteralPath $helper -PathType Leaf) "Config Default helper was not materialized"
        $probe = Join-Path $root "config-default-probe.ps1"
        $probeText = @'
param([Parameter(Mandatory=$true)][string]$HelperPath)
$ErrorActionPreference = "Stop"
. $HelperPath
$defaults = [ordered]@{ value = "default"; keep = "yes"; empty = ""; token = "secret" }
$file = [ordered]@{ value = "file"; fileOnly = $true; token = "file-secret" }
$environment = [ordered]@{ value = "environment"; environmentOnly = $true }
$cli = [ordered]@{ value = "cli"; cliOnly = $true }
$merged = Merge-KntConfigMaps -Maps @($defaults, $file, $environment, $cli)
if ($merged.value -ne "cli" -or $merged.keep -ne "yes" -or -not $merged.fileOnly -or -not $merged.environmentOnly -or -not $merged.cliOnly -or $merged.empty -ne "") { throw "Config precedence or unknown-key merge failed" }
$protected = Protect-KntConfigForDisplay -Config $merged -SecretKeys @("token")
if ($protected.token -ne "[REDACTED]" -or $merged.token -ne "file-secret" -or $defaults.token -ne "secret" -or $protected.keep -ne "yes") { throw "Config explicit redaction was not non-destructive" }
Write-Output "config-default-ok"
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $probeOutput = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $probe -HelperPath $helper 2>&1)
        Assert-Equal 0 $LASTEXITCODE "Config Default probe exit code"
        Assert-True (($probeOutput -join "`n") -match "config-default-ok") "Config Default probe did not complete"
    }
}
Invoke-TestCase "Logging Tool Default writes structured records to stderr" {
    Invoke-KntInitFixture -Profiles @("minimal") -Defaults @("logging") -AssertOutput {
        param($root, $output)
        $helper = Join-Path $root "project/tools/logging-default.ps1"
        Assert-True (Test-Path -LiteralPath $helper -PathType Leaf) "Logging Default helper was not materialized"
        $probe = Join-Path $root "logging-default-probe.ps1"
        $probeText = @'
param([Parameter(Mandatory=$true)][string]$HelperPath)
$ErrorActionPreference = "Stop"
. $HelperPath
$record = New-KntLogRecord -Level "warning" -Message "ready" -Data @{ source = "test" }
if ($record.level -ne "warning" -or $record.message -ne "ready" -or [string]::IsNullOrWhiteSpace($record.timestamp)) { throw "Log record was incomplete" }
[DateTimeOffset]::Parse($record.timestamp) | Out-Null
$sinkSeen = $null
$redacted = Invoke-KntLogSink -Record $record -Redactor { param($value) return [pscustomobject]@{ timestamp = $value.timestamp; level = $value.level; message = $value.message; data = @{ source = "redacted" } } } -Sink { param($value) $script:sinkSeen = $value; return $value }
if ($null -eq $sinkSeen -or $sinkSeen.data.source -ne "redacted" -or $redacted.data.source -ne "redacted") { throw "Log sink or redactor hook was not invoked" }
Write-KntConsoleLog -Record $record -Json
[Console]::Out.WriteLine("stdout-marker")
'@
        Set-Content -LiteralPath $probe -Value $probeText -Encoding UTF8
        $stderrPath = Join-Path $root "logging-default.stderr"
        $stdoutPath = Join-Path $root "logging-default.stdout"
        $arguments = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"' + $probe + '"'),
            "-HelperPath",
            ('"' + $helper + '"')
        )
        $process = Start-Process -FilePath $PowerShellExecutable -ArgumentList $arguments -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -Wait -PassThru
        Assert-Equal 0 $process.ExitCode "Logging Default probe exit code"
        $stdout = Get-Content -Raw -Encoding UTF8 $stdoutPath
        Assert-True ($stdout -match "stdout-marker") "Logging probe did not complete"
        $stderrText = Get-Content -Raw -Encoding UTF8 $stderrPath
        $jsonStart = $stderrText.IndexOf("{")
        $jsonEnd = $stderrText.LastIndexOf("}")
        Assert-True ($jsonStart -ge 0 -and $jsonEnd -gt $jsonStart) "Logging stderr did not contain a JSON record"
        $stderr = $stderrText.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
        Assert-Equal "warning" $stderr.level "structured log level"
        Assert-Equal "ready" $stderr.message "structured log message"
        Assert-True ($stdout -notmatch "ready|warning") "Logging polluted stdout"
    }
}
Invoke-TestCase "oneOf requires exactly one matching schema" {
    $schema = [pscustomobject]@{
        oneOf = @(
            [pscustomobject]@{ type = "string" },
            [pscustomobject]@{ type = "string"; minLength = 1 }
        )
    }
    $multipleMatches = @(Test-KntSchema -Data "abc" -Schema $schema -Path "fixture.value")
    Assert-Equal 1 $multipleMatches.Count "overlapping oneOf schema count"
    Assert-True ($multipleMatches[0] -match "exactly one.*matched 2") "multiple oneOf matches were not rejected"

    $zeroMatches = @(Test-KntSchema -Data 123 -Schema $schema -Path "fixture.value")
    Assert-Equal 1 $zeroMatches.Count "zero-match oneOf schema count"
    Assert-True ($zeroMatches[0] -match "exactly one.*matched 0") "zero oneOf matches were not rejected"
}
Invoke-TestCase "Base schemas use the declared validator keyword subset" {
    $supported = @(
        "type", "required", "properties", "additionalProperties", "items", "oneOf",
        "enum", "const", "pattern", "minLength", "uniqueItems", '$schema', '$id', "title"
    )
    $explicitlyExcluded = @('$ref')
    $unsupported = New-Object System.Collections.Generic.List[string]
    foreach ($schemaFile in Get-ChildItem (Join-Path $RepoRoot ".kinotch/schemas") -Filter "*.json" -File) {
        $schema = Get-Content -Raw -Encoding UTF8 $schemaFile.FullName | ConvertFrom-Json
        foreach ($keyword in @(Get-SchemaKeywordNames $schema)) {
            if ($keyword -notin $supported -and $keyword -notin $explicitlyExcluded) {
                [void]$unsupported.Add("$($schemaFile.Name):$keyword")
            }
        }
    }
    Assert-Equal 0 $unsupported.Count ("unsupported schema keywords: " + ($unsupported -join ", "))
}
Invoke-TestCase "invalid manifest is rejected by schema" {
    Invoke-KntFixture -Name "invalid-manifest" -Command "doctor" -ExpectedExit 1 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Schema validation failed") "schema error was not reported"
    }
}
Invoke-TestCase "invalid action registry is rejected by schema" {
    Invoke-KntFixture -Name "invalid-actions" -Command "doctor" -ExpectedExit 1 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Schema validation failed") "action schema heading was not reported"
        Assert-True ($output -match "actions") "action schema path was not reported"
    }
}
Invoke-TestCase "invalid surface registry is rejected by schema" {
    Invoke-KntFixture -Name "invalid-surfaces" -Command "doctor" -ExpectedExit 1 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Schema validation failed") "surface schema heading was not reported"
        Assert-True ($output -match "surfaces") "surface schema path was not reported"
    }
}
Invoke-TestCase "invalid JSON returns parse exit code" {
    Invoke-KntFixture -Name "invalid-json" -Command "doctor" -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "JSON parse error") "JSON parse error was not reported"
    }
}
Invoke-TestCase "missing required path is rejected" {
    Invoke-KntFixture -Name "missing-files" -Command "doctor" -ExpectedExit 1 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "MISSING path.*docs|docs.*MISSING path") "missing path was not reported"
    }
}
Invoke-TestCase "unknown command returns two" {
    Invoke-KntFixture -Name "valid-minimal" -Command "unknown-command" -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "Unknown command") "unknown command was not reported"
    }
}
Invoke-TestCase "project command exit code propagates" {
    Invoke-KntFixture -Name "command-failure" -Command "test" -ExpectedExit 7
}
Invoke-TestCase "project command preserves native stderr with success exit" {
    Invoke-KntFixture -Name "valid-minimal" -Command "test" -ExpectedExit 0 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{
            exec = $PowerShellExecutable
            args = @("-NoProfile", "-Command", "[Console]::Error.WriteLine('diagnostic')")
            cwd = "."
            forward_args = $false
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    }
}
Invoke-TestCase "structured command forwards metacharacters without injection" {
    $malicious = "; Set-Content injected.txt pwned; `$(Get-Date) | & echo escaped"
    Invoke-KntFixture -Name "valid-minimal" -Command "test" -Arguments @($malicious) -ExpectedExit 0 -Prepare {
        param($root)
        $recordScript = @'
param()
[IO.File]::WriteAllText("received-argument.txt", [string]$args[0], (New-Object System.Text.UTF8Encoding($false)))
'@
        [IO.File]::WriteAllText((Join-Path $root "project/record-argument.ps1"), $recordScript, (New-Object System.Text.UTF8Encoding($false)))
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.test = [pscustomobject]@{
            exec = $PowerShellExecutable
            args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "record-argument.ps1")
            cwd = "project"
            forward_args = $true
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        $receivedPath = Join-Path $root "project/received-argument.txt"
        Assert-Equal $malicious (Get-Content -Raw -Encoding UTF8 $receivedPath) "structured command argument"
        Assert-True (-not (Test-Path (Join-Path $root "project/injected.txt"))) "structured command executed injected text"
    }
}
Invoke-TestCase "legacy command rejects forwarded arguments explicitly" {
    Invoke-KntFixture -Name "command-cwd" -Command "test" -Arguments @("unsafe-argument") -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "structured.*forward|forward.*structured|legacy") "legacy forwarded argument rejection was not reported"
    }
}
Invoke-TestCase "verify fallback runs test then build" {
    Invoke-KntFixture -Name "verify-fallback" -Command "verify" -ExpectedExit 0 -AssertOutput {
        param($root, $output)
        $marker = Join-Path $root "project/command-order.txt"
        Assert-True (Test-Path $marker) "verify marker was not created"
        Assert-Equal ("test" + [Environment]::NewLine + "build") ((Get-Content -Raw $marker).Trim()) "verify order"
    }
}
Invoke-TestCase "verify fallback propagates a failing project command" {
    Invoke-KntFixture -Name "verify-fallback" -Command "verify" -ExpectedExit 9 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.commands.build.run = if (Get-Command pwsh -ErrorAction SilentlyContinue) {
            "& pwsh -NoProfile -Command 'exit 9'"
        } else {
            "& powershell -NoProfile -Command 'exit 9'"
        }
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    }
}
Invoke-TestCase "command runs in declared cwd" {
    Invoke-KntFixture -Name "command-cwd" -Command "test" -ExpectedExit 0 -AssertOutput {
        param($root, $output)
        $marker = Join-Path $root "project/command-cwd.marker"
        Assert-True (Test-Path $marker) "cwd marker was not created"
        $actual = (Get-Content -Raw $marker).Trim()
        $expected = (Resolve-Path (Join-Path $root "project")).Path
        Assert-Equal $expected $actual "command cwd"
    }
}

Invoke-TestCase "changed Base file fails base-check" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-check" -ExpectedExit 1 -Prepare {
        param($root)
        Set-FixtureBaseIndex $root
        Add-Content -LiteralPath (Join-Path $root ".kinotch/README_BASE.md") -Value "changed for test"
    }
}

Invoke-TestCase "base-refresh rejects protected changes without a version bump" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-refresh" -ExpectedExit 2 -Prepare {
        param($root)
        Set-FixtureAsBase $root
        Set-FixtureBaseIndex $root
        $expectedIndex = Join-Path $root "project/expected-base-files.json"
        $expectedInventory = Join-Path $root "project/expected-file-inventory.txt"
        Copy-Item -LiteralPath (Join-Path $root ".kinotch/base-files.json") -Destination $expectedIndex
        Copy-Item -LiteralPath (Join-Path $root ".kinotch/FILE_INVENTORY.txt") -Destination $expectedInventory
        Add-Content -LiteralPath (Join-Path $root ".kinotch/README_BASE.md") -Value "changed without version bump"
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "protected Base content changed without BASE_VERSION bump") "same-version protected change was not rejected"
        Assert-Equal (Get-Content -Raw -LiteralPath (Join-Path $root "project/expected-base-files.json")) (Get-Content -Raw -LiteralPath (Join-Path $root ".kinotch/base-files.json")) "base-files.json changed after rejected refresh"
        Assert-Equal (Get-Content -Raw -LiteralPath (Join-Path $root "project/expected-file-inventory.txt")) (Get-Content -Raw -LiteralPath (Join-Path $root ".kinotch/FILE_INVENTORY.txt")) "FILE_INVENTORY.txt changed after rejected refresh"
    }
}

Invoke-TestCase "base-check rejects a protected symlink file" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-check" -ExpectedExit 2 -Prepare {
        param($root)
        Set-FixtureBaseIndex $root
        $outside = Join-Path $root "outside-base-file.txt"
        Set-Content -LiteralPath $outside -Value "outside" -NoNewline
        $protected = Join-Path $root ".kinotch/README_BASE.md"
        Remove-Item -LiteralPath $protected -Force
        try {
            New-Item -ItemType SymbolicLink -Path $protected -Target $outside -ErrorAction Stop | Out-Null
        }
        catch {
            $script:SkipCurrentTest = $true
            Write-Host "[SKIP] symlink creation is unavailable: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } -AssertOutput {
        param($root, $output)
        if (-not $script:SkipCurrentTest) {
            Assert-True ($output -match "UNSAFE|symlink|junction|reparse|boundary") "protected symlink was not rejected"
        }
    }
}

Invoke-TestCase "base-refresh rejects a symlinked .kinotch boundary" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-refresh" -ExpectedExit 2 -Prepare {
        param($root)
        Set-FixtureAsBase $root
        Set-FixtureBaseIndex $root
        $realBase = Join-Path $root ".kinotch-real"
        Move-Item -LiteralPath (Join-Path $root ".kinotch") -Destination $realBase
        try {
            New-Item -ItemType SymbolicLink -Path (Join-Path $root ".kinotch") -Target $realBase -ErrorAction Stop | Out-Null
        }
        catch {
            $script:SkipCurrentTest = $true
            Write-Host "[SKIP] symlink creation is unavailable: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } -AssertOutput {
        param($root, $output)
        if (-not $script:SkipCurrentTest) {
            Assert-True ($output -match "symlink|junction|reparse|boundary") "symlinked .kinotch boundary was not rejected"
        }
    }
}

Invoke-TestCase "base-refresh indexes new common file after version bump" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-refresh" -ExpectedExit 0 -Prepare {
        param($root)
        Set-FixtureAsBase $root
        Set-FixtureBaseIndex $root
        Set-Content -LiteralPath (Join-Path $root ".kinotch/new-common.txt") -Value "new common file" -NoNewline
        Set-Content -LiteralPath (Join-Path $root ".kinotch/BASE_VERSION") -Value "0.5.10" -NoNewline
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        $before = @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root base-check 2>&1)
        if ($LASTEXITCODE -eq 0) { throw "unindexed Base file was not rejected: $($before -join ' ')" }
    } -AssertOutput {
        param($root, $output)
        $router = Join-Path $root ".kinotch/scripts/knt.ps1"
        @(& $PowerShellExecutable -NoProfile -ExecutionPolicy Bypass -File $router -RootOverride $root base-check 2>&1) | Out-Null
        Assert-Equal 0 $LASTEXITCODE "base-check after refresh"
    }
}

Invoke-TestCase "Base documentation and profile metadata are finalized" {
    $spec = Get-Content -Raw (Join-Path $RepoRoot "project/docs/SPEC.md")
    $state = Get-Content -Raw (Join-Path $RepoRoot "project/docs/CURRENT_STATE.md")
    $runtime = Get-Content -Raw (Join-Path $RepoRoot ".kinotch/RUNTIME_INTEGRATION.md")
    $baseReadme = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/README_BASE.md")
    $workflow = Get-Content -Raw (Join-Path $RepoRoot ".github/workflows/verify.yml")
    $surfaceRegistry = Get-Content -Raw (Join-Path $RepoRoot "project/contracts/surfaces.json") | ConvertFrom-Json
    $catalog = Get-Content -Raw -Encoding UTF8 (Join-Path $RepoRoot ".kinotch/defaults/catalog.json") | ConvertFrom-Json
    $baseVersion = (Get-Content -Raw (Join-Path $RepoRoot ".kinotch/BASE_VERSION")).Trim()
    Assert-True (([regex]::Matches($spec, "(?m)^\d+\. ")).Count -ge 10) "SPEC acceptance criteria are incomplete"
    Assert-True ($state -notmatch "Project-specific definition has not been filled") "CURRENT_STATE still contains a template placeholder"
    Assert-True ($state -match "Project Manifest / Action Registry / Surface Registry runtime schema validation") "CURRENT_STATE runtime validation wording is stale"
    Assert-True ($state -match "Error / Result / Progress / Resource / Artifact schema definitions") "CURRENT_STATE schema-definition wording is missing"
    Assert-True ($runtime -match "Action Result") "Runtime defined-contract content is missing"
    Assert-True ($runtime -match "ActionRequest") "Runtime candidate-contract content is missing"
    Assert-True ($workflow -match "knt\.ps1 setup") "Base CI setup step is missing"
    Assert-True ($workflow -match "actions/checkout@[0-9a-f]{40}(?:\s+#\s+v4)?") "Base Verify checkout action is not pinned to a full commit SHA"
    Assert-Equal 0 @($surfaceRegistry.surfaces.PSObject.Properties).Count "Base Surface Registry should be empty"
    Assert-Equal "0.5.9" $baseVersion "Base version"
    Assert-True ($baseReadme -match "Surface Default Kit") "README_BASE Surface Kit wording is missing"
    Assert-True ($baseReadme -match "OVERRIDE") "README_BASE override boundary is missing"
    Assert-True (@($catalog.defaults | Where-Object { $_.kind -eq "surface" }).Count -ge 8) "Surface Default catalog entries are incomplete"
    $toolIds = @($catalog.defaults | Where-Object { $_.kind -eq "tool" } | ForEach-Object { [string]$_.id } | Sort-Object)
    Assert-Equal 6 $toolIds.Count "Active Tool Default catalog count"
    Assert-Equal "ci-test,config,file-io,generated-integrity,logging,pwa" ($toolIds -join ",") "Active Tool Default catalog IDs"
    foreach ($profileFile in Get-ChildItem (Join-Path $RepoRoot ".kinotch/profiles") -File) {
        $profile = Get-Content -Raw -Encoding UTF8 $profileFile.FullName | ConvertFrom-Json
        Assert-True (-not $profile.PSObject.Properties["status"]) "$($profileFile.Name) has stale profile lifecycle metadata"
    }
}

Invoke-TestCase "profile surface contradiction fails doctor" {
    Invoke-KntFixture -Name "valid-minimal" -Command "doctor" -ExpectedExit 1 -Prepare {
        param($root)
        $manifestPath = Join-Path $root "project/project.json"
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        $manifest.profile = "cli"
        [IO.File]::WriteAllText($manifestPath, (ConvertTo-Json $manifest -Depth 20) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "CONTRADICTION") "profile surface contradiction was not reported"
    }
}

Invoke-TestCase "base-refresh is restricted to repository-base" {
    Invoke-KntFixture -Name "valid-minimal" -Command "base-refresh" -ExpectedExit 2 -AssertOutput {
        param($root, $output)
        Assert-True ($output -match "only available.*repository-base") "base-refresh restriction was not reported"
    }
}

Write-Host "Self-test summary: passed=$Passed failed=$Failed skipped=$Skipped"
if ($Failed -gt 0) { exit 1 }
exit 0
