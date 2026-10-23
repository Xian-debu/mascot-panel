# Create/remove the Start Menu shortcut for the app.
# Usage: powershell -File make-shortcut.ps1 -Target <exe> [-WorkDir <dir>] [-Remove]
# Keep this file ASCII-only: PowerShell 5.1 reads .ps1 as ANSI and mangles UTF-8 text.
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$WorkDir = '',
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$name = [string]([char]0x5929) + [char]0x9009 + [char]0x59EC
$dir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$lnk = Join-Path $dir ($name + '.lnk')

if ($Remove) {
    if (Test-Path -LiteralPath $lnk) {
        Remove-Item -LiteralPath $lnk -Force
        Write-Output ("shortcut-removed " + $lnk)
    } else {
        Write-Output 'shortcut-absent'
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $Target)) {
    Write-Output ("shortcut-target-missing " + $Target)
    exit 2
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $Target
if ($WorkDir) { $shortcut.WorkingDirectory = $WorkDir }
$shortcut.IconLocation = $Target + ',0'
$shortcut.Description = 'Mascot desktop pet'
$shortcut.Save()
Write-Output ("shortcut-created " + $lnk)
