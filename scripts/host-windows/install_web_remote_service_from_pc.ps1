param(
    [string]$BoardIp = "10.11.198.140",
    [string]$Key = "",
    [string]$KnownHosts = "",
    [string]$BoardPassword = "rock",
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
    [switch]$DisableStraightAssist,
    [switch]$Disable
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
$InstallDir = "/home/rock/road_repair_web_remote"
$ServiceName = "road-repair-web-remote.service"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $Root "rk3588_migration\versions\20260615_web_remote_autostart\logs"
$InstallLog = Join-Path $LogDir "install_web_remote_service_$Stamp.txt"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$SshOptions = @(
    "-i", $Key,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=$KnownHosts"
)

function Invoke-Board {
    param([string]$Command)
    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = ssh @SshOptions $Board $Command 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $OldPreference
    }
    $Output
    if ($ExitCode -ne 0) {
        throw "ssh command failed with exit code $ExitCode"
    }
}

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

if ($Disable) {
    $DisableCmd = "set +e; echo $BoardPassword | sudo -S systemctl disable --now $ServiceName; echo $BoardPassword | sudo -S systemctl reset-failed $ServiceName >/dev/null 2>&1; echo $BoardPassword | sudo -S ip link set can0 down >/dev/null 2>&1; systemctl is-enabled $ServiceName || true; systemctl is-active $ServiceName || true; ip -br link show can0 || true"
    Invoke-Board $DisableCmd 2>&1 | Tee-Object -FilePath $InstallLog
    Write-Host "Disabled $ServiceName"
    Write-Host "Log: $InstallLog"
    exit 0
}

Write-Host "Installing web remote autostart service on $Board"
Write-Host "Install dir: $InstallDir"
Write-Host "Service: $ServiceName"

Invoke-Board "set -e; echo $BoardPassword | sudo -S systemctl stop $ServiceName >/dev/null 2>&1 || true; echo $BoardPassword | sudo -S rm -rf $InstallDir; mkdir -p $InstallDir/logs; echo $BoardPassword | sudo -S chown -R rock:rock $InstallDir"
scp @SshOptions @Files "${Board}:$InstallDir/"

$StraightAssistArg = if ($DisableStraightAssist) { "--no-straight-assist" } else { "--straight-assist" }
$FeedbackJson = "$InstallDir/logs/motor_feedback.json"

$ServiceText = @"
[Unit]
Description=Road Repair browser remote safe-lock service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$InstallDir
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $InstallDir/road_repair_web_remote.py --host 0.0.0.0 --web-port $WebPort --current-limit $CurrentLimit --max-speed-rpm $MaxSpeedRpm --max-strafe-rpm $MaxStrafeRpm --max-rotate-rpm $MaxRotateRpm --forward-left-turn-compensation $ForwardLeftTurnCompensation --feedback-json $FeedbackJson --feedback-json-period-s 0.05 $StraightAssistArg --straight-assist-kp $StraightAssistKp --straight-assist-trim-limit $StraightAssistTrimLimit --straight-assist-max-feedback-age-s $StraightAssistMaxFeedbackAgeS --straight-assist-min-axis $StraightAssistMinAxis --straight-assist-min-rpm $StraightAssistMinRpm --rt-ping-timeout 90 --udp-peer-timeout 90 --gateway-log $InstallDir/logs/web_remote_gateway.log
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"@
$ServiceText = $ServiceText -replace "`r`n", "`n"
$ServiceText | ssh @SshOptions $Board "cat > /tmp/$ServiceName"

$InstallCmd = "set -e; echo $BoardPassword | sudo -S mv /tmp/$ServiceName /etc/systemd/system/$ServiceName; echo $BoardPassword | sudo -S chmod 644 /etc/systemd/system/$ServiceName; echo $BoardPassword | sudo -S systemctl daemon-reload; echo $BoardPassword | sudo -S systemctl enable --now $ServiceName; sleep 6; systemctl is-enabled $ServiceName; systemctl is-active $ServiceName; python3 - <<'PY'
import json
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:$WebPort/api/status', timeout=3).read().decode())
PY
ip -br link show can0 || true; pgrep -af '[r]oad_repair_web_remote.py|[c]an_gateway_service.py' || true"

Invoke-Board $InstallCmd 2>&1 | Tee-Object -FilePath $InstallLog

Write-Host "Open: http://$BoardIp`:$WebPort/"
Write-Host "Default startup mode is safe-lock. Use the web button to enable real motion."
Write-Host "Disable command:"
Write-Host "powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -BoardIp $BoardIp -Disable"
Write-Host "Log: $InstallLog"
