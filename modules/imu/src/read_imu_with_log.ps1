param(
    [string]$Python = "python",
    [string]$Port = "",
    [int]$Baud = 0,
    [double]$DurationS = 60
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$CaptureDir = Join-Path $ScriptDir "captures"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogDir "wt901c_read_$Timestamp.log"
$CsvPath = Join-Path $CaptureDir "wt901c_capture_$Timestamp.csv"

$ArgsList = @(
    (Join-Path $ScriptDir "read_wt901c_ttl.py"),
    "--duration-s", "$DurationS",
    "--output", $CsvPath
)

if ($Port) {
    $ArgsList += @("--port", $Port)
}
if ($Baud -gt 0) {
    $ArgsList += @("--baud", "$Baud")
}

Write-Host "Python: $Python"
Write-Host "Log: $LogPath"
Write-Host "CSV: $CsvPath"

$OldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$Output = & $Python @ArgsList 2>&1
$ExitCode = $LASTEXITCODE
$ErrorActionPreference = $OldErrorActionPreference
$Output | Tee-Object -FilePath $LogPath

if ($ExitCode -ne 0) {
    throw "WT901C read failed with exit code $ExitCode. See $LogPath"
}
