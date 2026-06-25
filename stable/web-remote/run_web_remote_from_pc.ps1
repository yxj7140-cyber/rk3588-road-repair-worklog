param(
    [string]$BoardIp = "10.11.198.140",
    [string]$Key = "",
    [string]$KnownHosts = "",
    [string]$BoardPassword = "rock",
    [string]$VersionName = "20260615_web_remote",
    [int]$WebPort = 8080,
    [int]$CurrentLimit = 1800,
    [int]$MaxSpeedRpm = 2000,
    [int]$MaxStrafeRpm = 1500,
    [int]$MaxRotateRpm = 1600,
    [double]$ForwardLeftTurnCompensation = 0.0,
    [double]$StraightAssistKp = 0.35,
    [double]$StraightAssistTrimLimit = 0.08,
    [double]$StraightAssistMaxFeedbackAgeS = 0.30,
    [double]$StraightAssistMinAxis = 0.12,
    [double]$StraightAssistMinRpm = 80.0,
    [int]$GatewaySeconds = 0,
    [switch]$EnableCurrent,
    [switch]$DisableStraightAssist,
    [switch]$StopOnly
)

$ErrorActionPreference = "Stop"

$ToolsDir = $PSScriptRoot
$Root = Split-Path -Parent $ToolsDir
if (-not $Key) {
    $Key = Join-Path $Root "board_ssh\rock5b_ed25519"
}
if (-not $KnownHosts) {
    $KnownHosts = Join-Path $Root "board_ssh\codex_wireless_known_hosts"
}

$Board = "rock@$BoardIp"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RemoteDir = "/tmp/rr_web_remote_$Stamp"
$ArchiveDir = Join-Path $Root "rk3588_migration\versions\$VersionName\logs"
$ModeName = if ($EnableCurrent) { "current_ground" } else { "safelock" }
$StdoutLog = Join-Path $ArchiveDir "web_remote_${ModeName}_stdout_$Stamp.txt"
$GatewayLog = "web_remote_${ModeName}_gateway_$Stamp.log"
$CleanupLog = Join-Path $ArchiveDir "web_remote_cleanup_$Stamp.txt"

New-Item -ItemType Directory -Force $ArchiveDir | Out-Null

$Files = @(
    "can_gateway_service.py",
    "chassis_vcmd_client.py",
    "road_repair_3508_model.py",
    "road_repair_vcmd_adapter.py",
    "road_repair_web_remote.py"
) | ForEach-Object { Join-Path $ToolsDir $_ }

foreach ($File in $Files) {
    if (-not (Test-Path $File)) {
        throw "Missing required file: $File"
    }
}

$SshOptions = @(
    "-i", $Key,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=$KnownHosts"
)

if ($StopOnly) {
    $StopCmd = "set +e; echo $BoardPassword | sudo -S systemctl stop road-repair-web-remote.service >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -9 -f '[r]oad_repair_web_remote.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -9 -f '[c]an_gateway_service.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S systemctl stop can-gateway.service >/dev/null 2>&1; echo $BoardPassword | sudo -S ip link set can0 down >/dev/null 2>&1; /bin/rm -rf /tmp/rr_web_remote_* 2>/dev/null; systemctl is-active road-repair-web-remote.service || true; systemctl is-active can-gateway.service || true; ip -br link show can0 || true; pgrep -af '[r]oad_repair_web_remote.py|[c]an_gateway_service.py' || true"
    ssh @SshOptions $Board $StopCmd 2>&1 |
        Tee-Object -FilePath $CleanupLog
    Write-Host "Cleanup log: $CleanupLog"
    exit 0
}

Write-Host "Board: $Board"
Write-Host "Remote temp dir: $RemoteDir"
Write-Host "Archive dir: $ArchiveDir"
Write-Host "Mode: $ModeName"
Write-Host "Web URL: http://$BoardIp`:$WebPort/"
Write-Host "Stop command: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -BoardIp $BoardIp -StopOnly"
if (-not $EnableCurrent) {
    Write-Host "Safety: safe-lock mode. Buttons will NOT output non-zero motor current."
}
else {
    Write-Host "WARNING: EnableCurrent is set. The web remote CAN move the chassis."
}

try {
    ssh @SshOptions $Board "set +e; echo $BoardPassword | sudo -S systemctl stop road-repair-web-remote.service >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -9 -f '[r]oad_repair_web_remote.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -9 -f '[c]an_gateway_service.py' >/dev/null 2>&1"
    ssh @SshOptions $Board "rm -rf $RemoteDir; mkdir -p $RemoteDir/logs"
    scp @SshOptions @Files "${Board}:$RemoteDir/"

    $RemoteGatewayLog = "$RemoteDir/logs/$GatewayLog"
    $StraightAssistArg = if ($DisableStraightAssist) { "--no-straight-assist" } else { "--straight-assist" }
    $FeedbackJson = "$RemoteDir/logs/motor_feedback.json"
    $Args = @(
        "--host 0.0.0.0",
        "--web-port $WebPort",
        "--current-limit $CurrentLimit",
        "--max-speed-rpm $MaxSpeedRpm",
        "--max-strafe-rpm $MaxStrafeRpm",
        "--max-rotate-rpm $MaxRotateRpm",
        "--forward-left-turn-compensation $ForwardLeftTurnCompensation",
        "--feedback-json $FeedbackJson",
        "--feedback-json-period-s 0.05",
        $StraightAssistArg,
        "--straight-assist-kp $StraightAssistKp",
        "--straight-assist-trim-limit $StraightAssistTrimLimit",
        "--straight-assist-max-feedback-age-s $StraightAssistMaxFeedbackAgeS",
        "--straight-assist-min-axis $StraightAssistMinAxis",
        "--straight-assist-min-rpm $StraightAssistMinRpm",
        "--gateway-log $RemoteGatewayLog"
    )
    if ($EnableCurrent) {
        $Args += "--enable-current"
    }

    $ArgLine = $Args -join ' '
    $StartScript = @"
#!/usr/bin/env bash
set -e
cd "$RemoteDir"
export SUDO_PASSWORD="$BoardPassword"
setsid python3 ./road_repair_web_remote.py $ArgLine > logs/web_remote_stdout.log 2>&1 < /dev/null &
echo `$! > logs/web_remote.pid
"@
    $StartScript = $StartScript -replace "`r`n", "`n"
    $StartScript | ssh @SshOptions $Board "cat > $RemoteDir/start_web_remote.sh && chmod +x $RemoteDir/start_web_remote.sh"
    ssh @SshOptions $Board "bash $RemoteDir/start_web_remote.sh"
    Start-Sleep -Seconds 4
    ssh @SshOptions $Board "cd $RemoteDir && cat logs/web_remote_stdout.log && echo '--- status ---' && python3 - <<'PY'
import json
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:$WebPort/api/status', timeout=2).read().decode())
PY
echo '--- processes ---' && pgrep -af '[r]oad_repair_web_remote.py|[c]an_gateway_service.py' && echo '--- can0 ---' && ip -br link show can0" 2>&1 |
        Tee-Object -FilePath $StdoutLog

    if ($GatewaySeconds -gt 0) {
        Write-Host "Keeping web remote alive for $GatewaySeconds seconds..."
        Start-Sleep -Seconds $GatewaySeconds
    }
    else {
        Write-Host "Web remote is running. Open: http://$BoardIp`:$WebPort/"
        Write-Host "Run this when finished:"
        Write-Host "powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -BoardIp $BoardIp -StopOnly"
        Write-Host "Stdout log: $StdoutLog"
        return
    }
}
finally {
    if ($GatewaySeconds -gt 0) {
        $CleanupCmd = "set +e; echo $BoardPassword | sudo -S pkill -9 -f '[r]oad_repair_web_remote.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -9 -f '[c]an_gateway_service.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S systemctl stop can-gateway.service >/dev/null 2>&1; echo $BoardPassword | sudo -S ip link set can0 down >/dev/null 2>&1; if [ -d '$RemoteDir/logs' ]; then true; fi; systemctl is-active can-gateway.service || true; ip -br link show can0 || true; pgrep -af '[r]oad_repair_web_remote.py|[c]an_gateway_service.py' || true"
        ssh @SshOptions $Board "cd $RemoteDir && tar -czf /tmp/rr_web_remote_${Stamp}_logs.tgz logs 2>/dev/null || true"
        scp @SshOptions "${Board}:/tmp/rr_web_remote_${Stamp}_logs.tgz" "$ArchiveDir\" 2>$null
        ssh @SshOptions $Board $CleanupCmd 2>&1 |
            Tee-Object -FilePath $CleanupLog
        ssh @SshOptions $Board "rm -rf $RemoteDir /tmp/rr_web_remote_${Stamp}_logs.tgz"
        Write-Host "Stdout log:  $StdoutLog"
        Write-Host "Cleanup log: $CleanupLog"
    }
}
