[CmdletBinding()]
param()

function Test-WindowsShellHost {
    return ($env:OS -eq "Windows_NT")
}

function Resolve-WindowsShellPath {
    param([Parameter(Mandatory=$true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Windows shell path cannot be empty."
    }
    return (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
}

function Convert-WindowsDropItems {
    param([string[]]$Paths = @())

    $normalized = New-Object System.Collections.Generic.List[string]
    foreach ($path in @($Paths)) {
        if ([string]::IsNullOrWhiteSpace([string]$path)) { continue }
        [void]$normalized.Add((Resolve-WindowsShellPath -Path ([string]$path)))
    }
    if ($normalized.Count -eq 0) { return $null }
    return @($normalized.ToArray())
}

function Select-WindowsPath {
    param(
        [ValidateSet("File", "Folder")][string]$Kind = "File",
        [AllowEmptyString()][string]$SelectedPath = "",
        [string]$InitialPath = "",
        [switch]$UseNativeDialog
    )

    if (-not [string]::IsNullOrWhiteSpace($SelectedPath)) {
        $resolved = Resolve-WindowsShellPath -Path $SelectedPath
        $item = Get-Item -LiteralPath $resolved -ErrorAction Stop
        if ($Kind -eq "File" -and $item.PSIsContainer) { throw "A file path was required." }
        if ($Kind -eq "Folder" -and -not $item.PSIsContainer) { throw "A folder path was required." }
        return $resolved
    }
    if (-not $UseNativeDialog) { return $null }
    if (-not (Test-WindowsShellHost)) { throw "Windows native picker is only available on Windows." }

    Add-Type -AssemblyName System.Windows.Forms
    if ($Kind -eq "File") {
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        if (-not [string]::IsNullOrWhiteSpace($InitialPath)) { $dialog.InitialDirectory = $InitialPath }
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            return (Resolve-WindowsShellPath -Path $dialog.FileName)
        }
        return $null
    }
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    if (-not [string]::IsNullOrWhiteSpace($InitialPath)) { $dialog.SelectedPath = $InitialPath }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return (Resolve-WindowsShellPath -Path $dialog.SelectedPath)
    }
    return $null
}

function Save-WindowsPath {
    param(
        [AllowEmptyString()][string]$SelectedPath = "",
        [string]$InitialPath = "",
        [switch]$UseNativeDialog
    )

    if (-not [string]::IsNullOrWhiteSpace($SelectedPath)) {
        return [IO.Path]::GetFullPath($SelectedPath)
    }
    if (-not $UseNativeDialog) { return $null }
    if (-not (Test-WindowsShellHost)) { throw "Windows native save dialog is only available on Windows." }

    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    if (-not [string]::IsNullOrWhiteSpace($InitialPath)) { $dialog.InitialDirectory = $InitialPath }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return [IO.Path]::GetFullPath($dialog.FileName)
    }
    return $null
}

function New-WindowsCancelSource {
    return [pscustomobject]@{ requested = $false }
}

function Request-WindowsCancel {
    param([Parameter(Mandatory=$true)]$Source)
    $Source.requested = $true
}

function Test-WindowsCancelRequested {
    param([Parameter(Mandatory=$true)]$Source)
    return ([bool]$Source.requested)
}

function New-WindowsProgressState {
    param(
        [string]$Stage = "",
        [int]$Total = 0
    )

    return [pscustomobject]@{
        stage = $Stage
        current = 0
        total = $Total
        message = ""
        status = "started"
    }
}

function Update-WindowsProgressState {
    param(
        [Parameter(Mandatory=$true)]$State,
        [int]$Current,
        [AllowEmptyString()][string]$Message = ""
    )

    $State.current = $Current
    $State.message = $Message
    $State.status = "progress"
}

function Complete-WindowsProgressState {
    param([Parameter(Mandatory=$true)]$State)

    if ([int]$State.total -gt 0) { $State.current = $State.total }
    $State.status = "completed"
}

function Fail-WindowsProgressState {
    param(
        [Parameter(Mandatory=$true)]$State,
        [AllowEmptyString()][string]$Message = ""
    )

    $State.message = $Message
    $State.status = "failed"
}

function Show-WindowsErrorDialog {
    param(
        [Parameter(Mandatory=$true)][string]$Message,
        [string]$Title = "Error"
    )

    if (-not (Test-WindowsShellHost)) { throw "Windows error dialog is only available on Windows." }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($Message, $Title, [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
}

function Reveal-WindowsPath {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-WindowsShellHost)) {
        throw "Windows shell Default is only available on Windows."
    }
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    Start-Process -FilePath "explorer.exe" -ArgumentList "/select,`"$resolved`""
}

function Copy-WindowsClipboardText {
    param([Parameter(Mandatory=$true)][string]$Text)

    if (-not (Test-WindowsShellHost)) {
        throw "Windows shell Default is only available on Windows."
    }
    Set-Clipboard -Value $Text
}
