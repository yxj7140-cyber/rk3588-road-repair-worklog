param(
    [string]$BoardIp = "10.11.198.140",
    [string]$Key = "",
    [string]$KnownHosts = "",
    [string]$BoardPassword = "rock",
    [string]$VersionName = "20260615_chassis_control_current_combo_lifted",
    [double]$Forward = 0.0,
    [double]$Strafe = 0.0,
    [double]$Rotate = 0.0,
    [double]$Duration = 0.25,
    [double]$Period = 0.02,
    [int]$CurrentLimit = 1200,
    [int]$MaxSpeedRpm = 0,
    [int]$MaxRotateRpm = 0,
    [int]$GatewaySeconds = 8,
    [string]$LogPrefix = "ground_axis",
    [switch]$EnableCurrent
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
$RemoteDir = "/tmp/ground_axis_$Stamp"
$ArchiveDir = Join-Path $Root "rk3588_migration\versions\$VersionName\logs"
$ModeName = if ($EnableCurrent) { "current_ground" } else { "safelock" }
$StdoutLog = Join-Path $ArchiveDir "${LogPrefix}_${ModeName}_stdout_$Stamp.txt"
$CleanupLog = Join-Path $ArchiveDir "${LogPrefix}_cleanup_$Stamp.txt"

New-Item -ItemType Directory -Force $ArchiveDir | Out-Null

$Files = @(
    "can_gateway_service.py",
    "chassis_vcmd_client.py",
    "road_repair_3508_model.py",
    "road_repair_vcmd_adapter.py",
    "chassis_control.py",
    "run_chassis_control_test.sh"
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

Write-Host "Board: $Board"
Write-Host "Remote temp dir: $RemoteDir"
Write-Host "Archive dir: $ArchiveDir"
Write-Host "Mode: $ModeName"
Write-Host "Axis: forward=$Forward strafe=$Strafe rotate=$Rotate duration=$Duration current_limit=$CurrentLimit"
if ($MaxSpeedRpm -gt 0 -or $MaxRotateRpm -gt 0) {
    Write-Host "Scale: max_speed_rpm=$MaxSpeedRpm max_rotate_rpm=$MaxRotateRpm"
}

try {
    ssh @SshOptions $Board "rm -rf $RemoteDir; mkdir -p $RemoteDir/logs"
    scp @SshOptions @Files "${Board}:$RemoteDir/"

    $RunArgs = @(
        "--forward $Forward",
        "--strafe $Strafe",
        "--rotate $Rotate",
        "--duration $Duration",
        "--period $Period",
        "--current-limit $CurrentLimit",
        "--gateway-seconds $GatewaySeconds",
        "--log-prefix ${LogPrefix}_${ModeName}_$Stamp"
    )
    if ($MaxSpeedRpm -gt 0) {
        $RunArgs += "--max-speed-rpm $MaxSpeedRpm"
    }
    if ($MaxRotateRpm -gt 0) {
        $RunArgs += "--max-rotate-rpm $MaxRotateRpm"
    }
    if ($EnableCurrent) {
        $RunArgs += "--enable-current"
    }

    $RunCmd = "cd $RemoteDir && chmod +x ./run_chassis_control_test.sh && LOG_DIR=$RemoteDir/logs SUDO_PASSWORD=$BoardPassword bash ./run_chassis_control_test.sh $($RunArgs -join ' ')"
    ssh @SshOptions $Board $RunCmd 2>&1 |
        Tee-Object -FilePath $StdoutLog

    scp @SshOptions "${Board}:$RemoteDir/logs/*" "$ArchiveDir\"

    $Analyzer = Join-Path $ToolsDir "analyze_can_gateway_log.ps1"
    if (Test-Path $Analyzer) {
        $RunLogs = Get-ChildItem -Path $ArchiveDir -Filter "${LogPrefix}_${ModeName}_${Stamp}_*.log" -File
        foreach ($RunLog in $RunLogs) {
            $AnalysisLog = Join-Path $ArchiveDir "$($RunLog.BaseName)_analysis.txt"
            & $Analyzer -LogPath $RunLog.FullName -OutFile $AnalysisLog
            Write-Host "Analysis log: $AnalysisLog"
        }
    }
}
finally {
    $CleanupCmd = "set +e; echo $BoardPassword | sudo -S systemctl stop can-gateway.service >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -f '[c]an_gateway_service.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S ip link set can0 down >/dev/null 2>&1; case '$RemoteDir' in /tmp/ground_axis_*) echo $BoardPassword | sudo -S /bin/rm -rf -- '$RemoteDir' ;; *) echo 'refuse cleanup: unexpected remote dir $RemoteDir' ;; esac; systemctl is-active can-gateway.service || true; ip -br link show can0 || true; pgrep -af '[c]an_gateway_service.py|[r]un_chassis|[c]hassis_control.py' || true; ls -d /tmp/ground_axis_* 2>/dev/null || true"
    ssh @SshOptions $Board $CleanupCmd 2>&1 |
        Tee-Object -FilePath $CleanupLog
}

Write-Host "Stdout log:  $StdoutLog"
Write-Host "Cleanup log: $CleanupLog"
