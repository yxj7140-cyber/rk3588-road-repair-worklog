param(
    [Parameter(Mandatory=$true)]
    [string]$BoardIp,
    [string]$User = "rock",
    [string]$BoardPassword = "rock",
    [string]$Key = "",
    [string]$KnownHosts = "",
    [string]$HyperBoot = "E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin",
    [switch]$SkipHyperBoot,
    [switch]$SkipWebRemote,
    [switch]$SkipFormalPackage
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

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $Root "rk3588_migration\reflash_restore\logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir "restore_after_reflash_$Stamp.log"

$Board = "$User@$BoardIp"
$SshOptions = @(
    "-i", $Key,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=$KnownHosts"
)

function Log-Line {
    param([string]$Text)
    $line = "$(Get-Date -Format 'HH:mm:ss') $Text"
    Write-Host $line
    Add-Content -LiteralPath $Log -Value $line
}

function Invoke-Board {
    param([string]$Command)
    Log-Line "ssh $Board :: $Command"
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = ssh @SshOptions $Board $Command 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $old
    }
    $output | Tee-Object -FilePath $Log -Append
    if ($code -ne 0) {
        throw "ssh command failed with exit code $code"
    }
}

function Copy-ToBoard {
    param(
        [string[]]$LocalPaths,
        [string]$RemotePath
    )
    Log-Line "scp -> ${Board}:$RemotePath"
    scp @SshOptions @LocalPaths "${Board}:$RemotePath" 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed with exit code $LASTEXITCODE"
    }
}

function Require-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file: $Path"
    }
}

Log-Line "Restore after official reflash"
Log-Line "Board: $Board"
Log-Line "Log: $Log"

Require-File $Key
if (-not $SkipHyperBoot) {
    Require-File $HyperBoot
}

Invoke-Board "hostname; id; ip -br addr; mkdir -p /home/rock/images /home/rock/incoming"

if (-not $SkipHyperBoot) {
    $remoteHyper = "/home/rock/images/HyperBoot_restore_$Stamp.bin"
    $md5 = (Get-FileHash -LiteralPath $HyperBoot -Algorithm MD5).Hash.ToLowerInvariant()
    Log-Line "HyperBoot MD5: $md5"
    Copy-ToBoard @($HyperBoot) $remoteHyper
    Invoke-Board "set -e; actual=`$(md5sum $remoteHyper | awk '{print `$1}'); echo `"$actual  $remoteHyper`"; test `"$actual`" = '$md5'; echo $BoardPassword | sudo -S mkdir -p /home/rock/images; if [ -f /boot/HyperBoot.bin ]; then echo $BoardPassword | sudo -S cp -a /boot/HyperBoot.bin /home/rock/images/HyperBoot_before_restore_$Stamp.bin; fi; echo $BoardPassword | sudo -S cp -f $remoteHyper /boot/HyperBoot.bin; sync; md5sum /boot/HyperBoot.bin"
}

$commonRuntimeFiles = @(
    "can_gateway_service.py",
    "chassis_vcmd_client.py",
    "road_repair_3508_model.py",
    "road_repair_vcmd_adapter.py"
) | ForEach-Object { Join-Path $ToolsDir $_ }

foreach ($file in $commonRuntimeFiles) { Require-File $file }

if (-not $SkipWebRemote) {
    $webFiles = @(
        $commonRuntimeFiles
        (Join-Path $ToolsDir "road_repair_web_remote.py")
    )
    foreach ($file in $webFiles) { Require-File $file }
    Invoke-Board "set -e; echo $BoardPassword | sudo -S systemctl stop road-repair-web-remote.service >/dev/null 2>&1 || true; echo $BoardPassword | sudo -S rm -rf /home/rock/road_repair_web_remote; mkdir -p /home/rock/road_repair_web_remote/logs"
    Copy-ToBoard $webFiles "/home/rock/road_repair_web_remote/"
    $service = @"
[Unit]
Description=Road Repair browser remote safe-lock service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/rock/road_repair_web_remote
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/rock/road_repair_web_remote/road_repair_web_remote.py --host 0.0.0.0 --web-port 8080 --current-limit 1800 --max-speed-rpm 2000 --max-strafe-rpm 1500 --max-rotate-rpm 1600 --forward-left-turn-compensation 0 --feedback-json /home/rock/road_repair_web_remote/logs/motor_feedback.json --feedback-json-period-s 0.05 --straight-assist --straight-assist-kp 0.35 --straight-assist-trim-limit 0.08 --straight-assist-max-feedback-age-s 0.3 --straight-assist-min-axis 0.12 --straight-assist-min-rpm 80 --rt-ping-timeout 90 --udp-peer-timeout 90 --gateway-log /home/rock/road_repair_web_remote/logs/web_remote_gateway.log
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"@
    $service = $service -replace "`r`n", "`n"
    $service | ssh @SshOptions $Board "cat > /tmp/road-repair-web-remote.service"
    if ($LASTEXITCODE -ne 0) {
        throw "failed to upload web remote service"
    }
    Invoke-Board "set -e; echo $BoardPassword | sudo -S mv /tmp/road-repair-web-remote.service /etc/systemd/system/road-repair-web-remote.service; echo $BoardPassword | sudo -S chmod 644 /etc/systemd/system/road-repair-web-remote.service; echo $BoardPassword | sudo -S systemctl daemon-reload; echo $BoardPassword | sudo -S systemctl enable --now road-repair-web-remote.service; sleep 5; systemctl is-enabled road-repair-web-remote.service; systemctl is-active road-repair-web-remote.service; python3 - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8080/api/status', timeout=3).read().decode())
PY"
}

if (-not $SkipFormalPackage) {
    $formalFiles = @(
        "can_gateway_service.py",
        "chassis_vcmd_client.py",
        "chassis_control.py",
        "road_repair_3508_model.py",
        "road_repair_vcmd_adapter.py",
        "road_repair_chassis_task.py",
        "road_repair_competition_behavior.py",
        "road_repair_competition_plan.py",
        "road_repair_competition_api.py",
        "road_repair_virtual_devices.py",
        "road_repair_virtual_mission.py",
        "road_repair_topic1_runner.py",
        "sample_road_repair_plan.txt",
        "sample_road_repair_scenario.json",
        "test_chassis_migration_core.py",
        "test_road_repair_migration.py",
        "run_road_repair_behavior_test.sh",
        "run_road_repair_chassis_task_test.sh",
        "run_road_repair_plan_test.sh",
        "run_road_repair_virtual_mission_test.sh",
        "run_road_repair_migration_selfcheck.sh"
    ) | ForEach-Object { Join-Path $ToolsDir $_ }
    foreach ($file in $formalFiles) { Require-File $file }
    Invoke-Board "set -e; rm -rf /home/rock/road_repair_chassis_migration; mkdir -p /home/rock/road_repair_chassis_migration/logs"
    Copy-ToBoard $formalFiles "/home/rock/road_repair_chassis_migration/"
    Invoke-Board "set -e; cd /home/rock/road_repair_chassis_migration; chmod +x ./*.sh; python3 -m py_compile ./*.py; bash ./run_road_repair_migration_selfcheck.sh"
}

Invoke-Board "set +e; echo '--- services ---'; systemctl is-active road-repair-web-remote.service; systemctl is-enabled road-repair-web-remote.service; systemctl is-active can-gateway.service; echo '--- can ---'; ip -br link show can0; echo '--- boot ---'; md5sum /boot/HyperBoot.bin 2>/dev/null; echo '--- dirs ---'; ls -ld /home/rock/road_repair_web_remote /home/rock/road_repair_chassis_migration /home/rock/images 2>/dev/null"

Log-Line "Restore finished."
Log-Line "Open web remote: http://$BoardIp`:8080/"
Log-Line "Default mode is safe-lock. Real motion still requires web confirmation."
