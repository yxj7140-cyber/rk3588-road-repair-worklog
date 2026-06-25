param(
    [string]$BoardIp = "10.21.50.12",
    [int]$WebPort = 8080,
    [string]$VersionName = "20260618_web_remote_feedback_straight_assist",
    [double]$Forward = 0.0,
    [double]$Strafe = 0.0,
    [double]$Rotate = 0.0,
    [double]$Duration = 0.45,
    [double]$Period = 0.05,
    [switch]$IUnderstandThisCanMoveMotors
)

$ErrorActionPreference = "Stop"

if (-not $IUnderstandThisCanMoveMotors) {
    throw "Refusing to run real motion. Re-run with -IUnderstandThisCanMoveMotors after the chassis area is safe."
}
if ($Duration -lt 0.05 -or $Duration -gt 5.0) {
    throw "Duration must be between 0.05 and 5.0 seconds."
}
if ($Period -lt 0.02 -or $Period -gt 0.25) {
    throw "Period must be between 0.02 and 0.25 seconds."
}

$ToolsDir = $PSScriptRoot
$Root = Split-Path -Parent $ToolsDir
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ArchiveDir = Join-Path $Root "rk3588_migration\versions\$VersionName\logs"
$OutFile = Join-Path $ArchiveDir "web_remote_motion_pulse_${Stamp}.json"
$Base = "http://$BoardIp`:$WebPort"

New-Item -ItemType Directory -Force $ArchiveDir | Out-Null

function Invoke-JsonPost {
    param(
        [string]$Path,
        [hashtable]$Body
    )
    $Json = $Body | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$Base$Path" -Method Post -ContentType "application/json" -Body $Json -TimeoutSec 5
}

$Result = [ordered]@{
    board_ip = $BoardIp
    web_port = $WebPort
    base_url = $Base
    stamp = $Stamp
    requested = [ordered]@{
        forward = $Forward
        strafe = $Strafe
        rotate = $Rotate
        duration = $Duration
        period = $Period
    }
    events = @()
}

try {
    $statusBefore = Invoke-RestMethod -Uri "$Base/api/status" -TimeoutSec 5
    $Result.status_before = $statusBefore
    $Result.events += [ordered]@{ type = "status_before"; time = (Get-Date).ToString("o"); mode = $statusBefore.mode; enable_current = $statusBefore.enable_current }

    $enable = Invoke-JsonPost "/api/enable_current" @{}
    $Result.enable_current = $enable
    $Result.events += [ordered]@{ type = "enable_current"; time = (Get-Date).ToString("o"); mode = $enable.mode; enable_current = $enable.enable_current }

    if (-not $enable.enable_current) {
        throw "Web remote did not enter current-enabled mode."
    }

    $deadline = (Get-Date).AddSeconds($Duration)
    $driveResponses = New-Object System.Collections.Generic.List[object]
    while ((Get-Date) -lt $deadline) {
        $response = Invoke-JsonPost "/api/drive" @{ forward = $Forward; strafe = $Strafe; rotate = $Rotate }
        $driveResponses.Add($response)
        Start-Sleep -Milliseconds ([int]([Math]::Max(20, $Period * 1000.0)))
    }
    $Result.drive_responses = $driveResponses
    $Result.events += [ordered]@{ type = "drive_loop_done"; time = (Get-Date).ToString("o"); packets = $driveResponses.Count }
}
finally {
    try {
        $Result.stop = Invoke-JsonPost "/api/stop" @{}
        $Result.events += [ordered]@{ type = "stop"; time = (Get-Date).ToString("o"); mode = $Result.stop.mode; enable_current = $Result.stop.enable_current }
    }
    catch {
        $Result.stop_error = $_.Exception.Message
    }

    try {
        $Result.safe_lock = Invoke-JsonPost "/api/safe_lock" @{}
        $Result.events += [ordered]@{ type = "safe_lock"; time = (Get-Date).ToString("o"); mode = $Result.safe_lock.mode; enable_current = $Result.safe_lock.enable_current }
    }
    catch {
        $Result.safe_lock_error = $_.Exception.Message
    }

    try {
        $Result.status_after = Invoke-RestMethod -Uri "$Base/api/status" -TimeoutSec 5
        $Result.events += [ordered]@{ type = "status_after"; time = (Get-Date).ToString("o"); mode = $Result.status_after.mode; enable_current = $Result.status_after.enable_current }
    }
    catch {
        $Result.status_after_error = $_.Exception.Message
    }

    $Result | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $OutFile -Encoding UTF8
}

Write-Host "Motion pulse completed."
Write-Host "Log: $OutFile"
Write-Host "Requested axes: forward=$Forward strafe=$Strafe rotate=$Rotate duration=$Duration period=$Period"
Write-Host "Drive packets: $($Result.drive_responses.Count)"
Write-Host "Final mode: $($Result.status_after.mode)"
Write-Host "Final enable_current: $($Result.status_after.enable_current)"
if ($Result.drive_responses.Count -gt 0) {
    $last = $Result.drive_responses[$Result.drive_responses.Count - 1]
    Write-Host "Last command rpm: f=$($last.forward_rpm) s=$($last.strafe_rpm) r=$($last.rotate_rpm)"
    Write-Host "Last assist: reason=$($last.straight_assist.reason) trim=$($last.straight_assist.trim)"
}
