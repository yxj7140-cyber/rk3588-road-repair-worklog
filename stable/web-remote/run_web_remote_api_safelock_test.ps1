param(
    [string]$BoardIp = "10.21.50.12",
    [int]$WebPort = 8080,
    [string]$VersionName = "20260618_web_remote_feedback_straight_assist"
)

$ErrorActionPreference = "Stop"

$ToolsDir = $PSScriptRoot
$Root = Split-Path -Parent $ToolsDir
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ArchiveDir = Join-Path $Root "rk3588_migration\versions\$VersionName\logs"
$OutFile = Join-Path $ArchiveDir "web_remote_api_safelock_$Stamp.json"
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
    tests = [ordered]@{}
}

$Result.tests.status_before = Invoke-RestMethod -Uri "$Base/api/status" -TimeoutSec 5
if ($Result.tests.status_before.enable_current) {
    throw "Refusing safelock API test because web remote is already current-enabled."
}

$Result.tests.forward = Invoke-JsonPost "/api/drive" @{ forward = 0.4; strafe = 0.0; rotate = 0.0 }
Start-Sleep -Milliseconds 120
$Result.tests.forward_rotate = Invoke-JsonPost "/api/drive" @{ forward = 0.4; strafe = 0.0; rotate = 0.4 }
Start-Sleep -Milliseconds 120
$Result.tests.forward_strafe = Invoke-JsonPost "/api/drive" @{ forward = 0.4; strafe = 0.35; rotate = 0.0 }
Start-Sleep -Milliseconds 120
$Result.tests.strafe_rotate = Invoke-JsonPost "/api/drive" @{ forward = 0.0; strafe = 0.35; rotate = -0.35 }
Start-Sleep -Milliseconds 120
$Result.tests.stop = Invoke-JsonPost "/api/stop" @{}
Start-Sleep -Milliseconds 120
$Result.tests.status_after = Invoke-RestMethod -Uri "$Base/api/status" -TimeoutSec 5

$JsonOut = $Result | ConvertTo-Json -Depth 12
$JsonOut | Set-Content -LiteralPath $OutFile -Encoding UTF8

Write-Host "Safe-lock web API test completed."
Write-Host "Log: $OutFile"
Write-Host "Mode before: $($Result.tests.status_before.mode)"
Write-Host "Mode after:  $($Result.tests.status_after.mode)"
Write-Host "Forward rpm: $($Result.tests.forward.forward_rpm)"
Write-Host "Forward+rotate rpm: f=$($Result.tests.forward_rotate.forward_rpm) r=$($Result.tests.forward_rotate.rotate_rpm)"
Write-Host "Forward+strafe rpm: f=$($Result.tests.forward_strafe.forward_rpm) s=$($Result.tests.forward_strafe.strafe_rpm)"
Write-Host "Strafe+rotate rpm: s=$($Result.tests.strafe_rotate.strafe_rpm) r=$($Result.tests.strafe_rotate.rotate_rpm)"
